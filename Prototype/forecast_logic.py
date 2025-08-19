import pandas as pd
import numpy as np
from prophet import Prophet
import json
from datetime import timedelta
import matplotlib.pyplot as plt
import os

# Load and prepare data
input_file = r'C:\Users\sghos\Desktop\Park\Prototype\inventory_data.csv'  # Absolute path
try:
    df = pd.read_csv(input_file)
except FileNotFoundError:
    print(f"Error: The file {input_file} was not found. Please check the path.")
    exit(1)
except Exception as e:
    print(f"Error loading {input_file}: {e}")
    exit(1)

# Parse date and time with adjustment for hours > 23
df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d')
df['time_hours'] = df['time'].apply(lambda x: int(x.split(':')[0]))
df['time_minutes'] = df['time'].apply(lambda x: int(x.split(':')[1]))
df['adjusted_time'] = df.apply(lambda row: f"{(row['time_hours'] % 24):02d}:{row['time_minutes']:02d}", axis=1)
df['datetime'] = pd.to_datetime(df['date'].astype(str) + ' ' + df['adjusted_time'], format='%Y-%m-%d %H:%M', errors='coerce')
if df['datetime'].isnull().any():
    print(f"Warning: {df['datetime'].isnull().sum()} rows had invalid datetime values and were dropped.")
    df = df.dropna(subset=['datetime'])

# Calculate warehouse-specific statistics
df['volume'] = df['x_length_m'] * df['y_length_m'] * df['z_height_m']
warehouse_stats = df.groupby('warehouse_name').agg({'stock': ['mean', 'min', 'max'], 'volume': 'mean'}).reset_index()
warehouse_stats.columns = ['warehouse_name', 'mean_stock', 'min_stock', 'max_stock', 'mean_volume']

# Define thresholds: overstock = mean + 35, understock = mean - 60, unique per warehouse
warehouse_stats['over_threshold'] = warehouse_stats['mean_stock'] + 35
warehouse_stats['under_threshold'] = warehouse_stats['mean_stock'] - 60
warehouse_stats['under_threshold'] = warehouse_stats['under_threshold'].apply(lambda x: max(x, 0))  # Avoid negative

# Dictionary for quick lookup
thresholds = dict(zip(warehouse_stats['warehouse_name'], 
                      zip(warehouse_stats['over_threshold'], warehouse_stats['under_threshold'])))

# Configurable forecast period (e.g., Diwali season)
forecast_start_date = pd.to_datetime('2025-10-20')  # Set desired start month/day
forecast_period_days = 40  # Set duration (e.g., Oct 20 to Nov 30, 2025)

# Process each warehouse
results = {}
for warehouse in df['warehouse_name'].unique():
    df_wh = df[df['warehouse_name'] == warehouse].sort_values('datetime')
    df_daily = df_wh.resample('D', on='datetime')['stock'].mean().reset_index()
    df_daily = df_daily.rename(columns={'datetime': 'ds', 'stock': 'y'})

    # Fit Prophet model with adjusted parameters
    try:
        model = Prophet(weekly_seasonality=True, daily_seasonality=False, yearly_seasonality=False, seasonality_prior_scale=5, seasonality_mode='additive')
        model.add_seasonality(name='diwali', period=365.25/12, fourier_order=10)  # Strong Diwali effect
        model.fit(df_daily)
    except Exception as e:
        print(f"Error fitting Prophet model for {warehouse}: {e}")
        continue

    # Forecast from the specified start date for the given period
    last_date = df_daily['ds'].max()
    current_time = pd.to_datetime('2025-08-19 16:07:00')  # Updated to current time (04:07 PM IST)
    start_forecast = max(last_date, current_time) if last_date else current_time
    if forecast_start_date < start_forecast:
        print(f"Warning: Forecast start date {forecast_start_date} is before last data point {start_forecast}. Using {forecast_start_date}.")
    future = model.make_future_dataframe(periods=forecast_period_days, include_history=False)
    future['ds'] = future['ds'] + (forecast_start_date - future['ds'].min())  # Shift to start date
    forecast = model.predict(future)
    forecast_df = forecast[['ds', 'yhat', 'trend', 'weekly', 'diwali']].tail(forecast_period_days)  # Only future dates

    # Save forecast data as CSV for the warehouse
    forecast_csv_path = os.path.join('Prototype', 'forecast_data', f'forecast_{warehouse.replace(" ", "_")}.csv')
    os.makedirs(os.path.dirname(forecast_csv_path), exist_ok=True)
    forecast_df.to_csv(forecast_csv_path, index=False)
    print(f"Saved forecast data for {warehouse} to {forecast_csv_path}")

    # Average seasonal for comparison
    avg_weekly = forecast_df['weekly'].mean()

    # Detect over/understock with explanations
    over_threshold, under_threshold = thresholds[warehouse]
    overstock_info = []
    understock_info = []
    for _, row in forecast_df.iterrows():
        date_str = row['ds'].strftime('%Y-%m-%d')
        yhat = row['yhat']
        trend = row['trend']
        seasonal = row['weekly']
        diwali_effect = row['diwali']
        
        if yhat > over_threshold:
            reason = []
            if seasonal > avg_weekly:
                reason.append(f"seasonal peak (weekly component: {seasonal:.2f} > average {avg_weekly:.2f})")
            if diwali_effect > 0:
                reason.append(f"Diwali effect (component: {diwali_effect:.2f})")
            if trend > df_daily['y'].mean():
                reason.append(f"upward trend contribution ({trend:.2f} > historical mean {df_daily['y'].mean():.2f})")
            if not reason:
                reason.append("combined model factors exceeding threshold")
            overstock_info.append({'date': date_str, 'forecasted_stock': yhat, 'explanation': ' and '.join(reason)})
        
        if yhat < under_threshold:
            reason = []
            if seasonal < avg_weekly:
                reason.append(f"seasonal trough (weekly component: {seasonal:.2f} < average {avg_weekly:.2f})")
            if trend < df_daily['y'].mean():
                reason.append(f"downward trend contribution ({trend:.2f} < historical mean {df_daily['y'].mean():.2f})")
            if not reason:
                reason.append("combined model factors below threshold")
            understock_info.append({'date': date_str, 'forecasted_stock': yhat, 'explanation': ' and '.join(reason)})

    results[warehouse] = {
        'overstock_info': overstock_info,
        'understock_info': understock_info,
        'mean_stock': float(warehouse_stats.loc[warehouse_stats['warehouse_name'] == warehouse, 'mean_stock'].iloc[0]),
        'over_threshold': over_threshold,
        'under_threshold': under_threshold
    }

    # Debug: Print threshold and sample forecast values
    print(f"{warehouse}: mean_stock={results[warehouse]['mean_stock']:.2f}, "
          f"over_threshold={over_threshold}, under_threshold={under_threshold}")
    print(f"Sample forecast range: min={forecast_df['yhat'].min():.2f}, max={forecast_df['yhat'].max():.2f}")
    print(f"Forecast start date: {forecast_df['ds'].min().strftime('%Y-%m-%d')}")

    # Plot and save graph with adjusted y-limits
    plt.figure(figsize=(10, 6))
    plt.plot(df_daily['ds'], df_daily['y'], label='Historical')
    plt.plot(forecast_df['ds'], forecast_df['yhat'], label='Forecast')
    plt.axhline(over_threshold, color='r', linestyle='--', label=f'Overstock Threshold ({over_threshold:.0f})')
    plt.axhline(under_threshold, color='g', linestyle='--', label=f'Understock Threshold ({under_threshold:.0f})')
    plt.ylim(min(under_threshold * 0.9, forecast_df['yhat'].min() * 0.9), max(over_threshold * 1.1, forecast_df['yhat'].max() * 1.1))
    plt.title(f'{warehouse} Forecast ({forecast_start_date.strftime("%b %d, %Y")} - {(forecast_start_date + timedelta(days=forecast_period_days-1)).strftime("%b %d, %Y")})')
    plt.xlabel('Date')
    plt.ylabel('Stock Level')
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    plot_dir = os.path.join('Prototype', 'static', 'plots')
    os.makedirs(plot_dir, exist_ok=True)
    plt.savefig(os.path.join(plot_dir, f'forecast_{warehouse.replace(" ", "_")}.png'))
    plt.close()

# Save to JSON at specified absolute path with debug check
json_path = r'C:\Users\sghos\Desktop\Park\Prototype\forecast_status.json'
json_dir = os.path.dirname(json_path)
os.makedirs(json_dir, exist_ok=True)
try:
    with open(json_path, 'w') as f:
        json.dump(results, f, default=str)
    print(f"Successfully wrote to '{json_path}'")
except Exception as e:
    print(f"Failed to write to '{json_path}': {e}")

# Save to CSV in Prototype
flattened_results = []
for warehouse, data in results.items():
    for item in data['overstock_info']:
        flattened_results.append({
            'warehouse_name': warehouse,
            'date': item['date'],
            'status': 'overstock',
            'forecasted_stock': item['forecasted_stock'],
            'explanation': item['explanation']
        })
    for item in data['understock_info']:
        flattened_results.append({
            'warehouse_name': warehouse,
            'date': item['date'],
            'status': 'understock',
            'forecasted_stock': item['forecasted_stock'],
            'explanation': item['explanation']
        })
df_results = pd.DataFrame(flattened_results)
df_results.to_csv(os.path.join('Prototype', 'forecast_structured.csv'), index=False)

# Create and update summary CSV with stocks to order
summary_data = []
for warehouse, data in results.items():
    under_threshold = data['under_threshold']
    understock_info = data['understock_info']
    stocks_to_order = sum(under_threshold - entry['forecasted_stock'] for entry in understock_info)
    summary_data.append({
        'warehouse_name': warehouse,
        'mean_stock': data['mean_stock'],
        'over_threshold': data['over_threshold'],
        'under_threshold': under_threshold,
        'overstock_count': len(data['overstock_info']),
        'understock_count': len(data['understock_info']),
        'stocks to order': stocks_to_order
    })

df_summary = pd.DataFrame(summary_data)
df_summary.to_csv(os.path.join('Prototype', 'forecast_summary.csv'), index=False)

print(f"Results saved to '{json_path}'")
print("Summary saved to 'Prototype/forecast_summary.csv'")
print("Graphs saved in 'Prototype/static/plots' as 'forecast_[warehouse_name].png' for each warehouse")