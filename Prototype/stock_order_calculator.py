import json
import pandas as pd
import os

# Define paths
FORECAST_STATUS_PATH = r'C:\Users\sghos\Desktop\Park\Prototype\forecast_status.json'
FORECAST_SUMMARY_PATH = os.path.join('Prototype', 'forecast_summary.csv')

# Load forecast results
try:
    with open(FORECAST_STATUS_PATH, 'r') as f:
        results = json.load(f)
except FileNotFoundError:
    print(f"Error: {FORECAST_STATUS_PATH} not found. Please run the forecast script first.")
    exit(1)
except Exception as e:
    print(f"Error loading {FORECAST_STATUS_PATH}: {e}")
    exit(1)

# Calculate stock to order for each warehouse
stock_to_order_data = {}
for warehouse, data in results.items():
    under_threshold = data['under_threshold']
    understock_info = data['understock_info']
    stocks_to_order = sum(under_threshold - entry['forecasted_stock'] for entry in understock_info)

    stock_to_order_data[warehouse] = stocks_to_order

    # Debug print
    print(f"{warehouse}: Stocks to order = {stocks_to_order:.2f}")

# Update the summary CSV with the new "stocks to order" column
try:
    # Read the existing summary CSV
    df_summary = pd.read_csv(FORECAST_SUMMARY_PATH)
    
    # Insert the new column "stocks to order" after "understock_count"
    understock_count_idx = df_summary.columns.get_loc('understock_count')
    df_summary.insert(understock_count_idx + 1, 'stocks to order', 
                      [stock_to_order_data.get(warehouse, 0) for warehouse in df_summary['warehouse_name']])
    
    # Save the updated CSV
    df_summary.to_csv(FORECAST_SUMMARY_PATH, index=False)
    print(f"Updated {FORECAST_SUMMARY_PATH} with 'stocks to order' column.")
except FileNotFoundError:
    print(f"Error: {FORECAST_SUMMARY_PATH} not found. Please ensure the forecast script ran first.")
except Exception as e:
    print(f"Error updating {FORECAST_SUMMARY_PATH}: {e}")