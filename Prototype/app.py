from flask import Flask, render_template, send_file, url_for
import pandas as pd
import os
from datetime import datetime
import pytz
import json

app = Flask(__name__)

# Define the path to the forecast summary file
FORECAST_SUMMARY_PATH = os.path.join('Prototype', 'forecast_summary.csv')

@app.route('/')
def home():
    # Read the CSV file
    try:
        df = pd.read_csv(FORECAST_SUMMARY_PATH)
        # Best-effort: compute overstock_excess from JSON if missing
        if 'overstock_excess' not in df.columns:
            try:
                with open('forecast_status.json', 'r') as f:
                    status_data = json.load(f)
                warehouse_to_excess = {}
                for warehouse_name, data in status_data.items():
                    over_threshold = data.get('over_threshold', 0)
                    overstock_info = data.get('overstock_info', [])
                    total_excess = sum(item.get('forecasted_stock', 0) - over_threshold for item in overstock_info)
                    warehouse_to_excess[warehouse_name] = total_excess
                df['overstock_excess'] = df['warehouse_name'].map(warehouse_to_excess).fillna(0)
            except Exception:
                df['overstock_excess'] = 0

        # Create human-readable status text
        def make_status(row):
            over_excess = float(row.get('overstock_excess', 0) or 0)
            under_need = float(row.get('stocks to order', 0) or 0)
            over_excess_int = int(round(over_excess))
            under_need_int = int(round(under_need))
            if over_excess_int > 0 and under_need_int == 0:
                return f"Overstocking by {over_excess_int} units"
            if under_need_int > 0 and over_excess_int == 0:
                return f"Understocking by {under_need_int} units"
            if over_excess_int > 0 and under_need_int > 0:
                return f"Mixed: over by {over_excess_int}, under by {under_need_int} units"
            return "On target"

        df['status'] = df.apply(make_status, axis=1)

        # Load detailed status to compute next actions
        try:
            with open('forecast_status.json', 'r') as f:
                status_data = json.load(f)
        except Exception:
            status_data = {}

        def compute_next_action(warehouse_name: str) -> str:
            data = status_data.get(warehouse_name, {})
            under_threshold = data.get('under_threshold', None)
            over_threshold = data.get('over_threshold', None)
            next_under = None
            next_over = None
            # Find next understock event
            for item in sorted(data.get('understock_info', []), key=lambda x: x.get('date', '9999-12-31')):
                try:
                    short_by = max(0, (under_threshold or 0) - float(item.get('forecasted_stock', 0)))
                except Exception:
                    short_by = 0
                next_under = (item.get('date'), int(round(short_by)))
                break
            # Find next overstock event
            for item in sorted(data.get('overstock_info', []), key=lambda x: x.get('date', '9999-12-31')):
                try:
                    excess_by = max(0, float(item.get('forecasted_stock', 0)) - (over_threshold or 0))
                except Exception:
                    excess_by = 0
                next_over = (item.get('date'), int(round(excess_by)))
                break

            if next_under and (not next_over or next_under[0] <= next_over[0]):
                return f"Order {next_under[1]} by {next_under[0]}"
            if next_over:
                return f"Reduce {next_over[1]} by {next_over[0]}"
            return "No action needed"

        df['next_action'] = df['warehouse_name'].apply(compute_next_action)

        # Reorder columns: warehouse_name, status, next_action, then the rest
        cols = df.columns.tolist()
        ordered = ['warehouse_name', 'status', 'next_action'] + [c for c in cols if c not in ['warehouse_name', 'status', 'next_action']]
        df = df[ordered]
        # Convert for template rendering
        rows = df.to_dict(orient='records')
        # Compute dashboard stats
        try:
            num_over = sum(1 for r in rows if isinstance(r.get('status'), str) and 'Overstocking' in r['status'])
            num_under = sum(1 for r in rows if isinstance(r.get('status'), str) and 'Understocking' in r['status'])
            num_mixed = sum(1 for r in rows if isinstance(r.get('status'), str) and 'Mixed' in r['status'])
            num_ok = sum(1 for r in rows if isinstance(r.get('status'), str) and 'On target' in r['status'])
            total_order = int(round(sum(float(r.get('stocks to order', 0) or 0) for r in rows)))
            total_excess = int(round(sum(float(r.get('overstock_excess', 0) or 0) for r in rows)))
            dashboard_stats = {
                'over': num_over,
                'under': num_under,
                'mixed': num_mixed,
                'ok': num_ok,
                'total_order': total_order,
                'total_excess': total_excess
            }
        except Exception:
            dashboard_stats = {'over': 0, 'under': 0, 'mixed': 0, 'ok': 0, 'total_order': 0, 'total_excess': 0}

        # Get current timestamp in IST using timezone
        ist = pytz.timezone('Asia/Kolkata')
        timestamp = datetime.now(ist).strftime('%Y-%m-%d %I:%M %p IST')
        return render_template('index.html', rows=rows, timestamp=timestamp, dashboard_stats=dashboard_stats)
    except FileNotFoundError:
        ist = pytz.timezone('Asia/Kolkata')
        timestamp = datetime.now(ist).strftime('%Y-%m-%d %I:%M %p IST')
        return render_template('index.html', rows=None, timestamp=timestamp, error="Forecast summary file not found. Please run the forecast script first.")
    except pd.errors.EmptyDataError:
        ist = pytz.timezone('Asia/Kolkata')
        timestamp = datetime.now(ist).strftime('%Y-%m-%d %I:%M %p IST')
        return render_template('index.html', rows=None, timestamp=timestamp, error="Forecast summary file is empty. Please ensure data is generated.")
    except Exception as e:
        ist = pytz.timezone('Asia/Kolkata')
        timestamp = datetime.now(ist).strftime('%Y-%m-%d %I:%M %p IST')
        return render_template('index.html', rows=None, timestamp=timestamp, error=f"Error loading forecast summary: {str(e)}"), 500

@app.route('/download')
def download_file():
    try:
        return send_file(FORECAST_SUMMARY_PATH, as_attachment=True, download_name='forecast_summary.csv')
    except FileNotFoundError:
        return "Error: forecast_summary.csv not found. Please run the forecast script first.", 404

@app.route('/api/summary')
def api_summary():
    try:
        df = pd.read_csv(FORECAST_SUMMARY_PATH)
        return df.to_json(orient='records')
    except FileNotFoundError:
        return {"error": "forecast_summary.csv not found"}, 404

@app.route('/warehouse/<warehouse_slug>')
def warehouse_detail(warehouse_slug: str):
    # Decode warehouse name and load data
    warehouse_name = warehouse_slug.replace('_', ' ')
    try:
        with open('forecast_status.json', 'r') as f:
            status_data = json.load(f)
    except Exception:
        status_data = {}

    try:
        df = pd.read_csv(FORECAST_SUMMARY_PATH)
        row = df[df['warehouse_name'] == warehouse_name].iloc[0].to_dict()
    except Exception:
        row = {}

    data = status_data.get(warehouse_name, {})
    under_threshold = data.get('under_threshold')
    over_threshold = data.get('over_threshold')

    # Compute next events
    def parse_date(d):
        try:
            return datetime.strptime(d, '%Y-%m-%d')
        except Exception:
            return None

    next_under = None
    for item in sorted(data.get('understock_info', []), key=lambda x: x.get('date', '9999-12-31')):
        d = parse_date(item.get('date'))
        if not d:
            continue
        short_by = max(0, (under_threshold or 0) - float(item.get('forecasted_stock', 0)))
        next_under = {'date': item.get('date'), 'short_by': int(round(short_by)), 'forecasted': float(item.get('forecasted_stock', 0))}
        break

    next_over = None
    for item in sorted(data.get('overstock_info', []), key=lambda x: x.get('date', '9999-12-31')):
        d = parse_date(item.get('date'))
        if not d:
            continue
        excess_by = max(0, float(item.get('forecasted_stock', 0)) - (over_threshold or 0))
        next_over = {'date': item.get('date'), 'excess_by': int(round(excess_by)), 'forecasted': float(item.get('forecasted_stock', 0))}
        break

    # Build image path
    image_filename = f"plots/forecast_{warehouse_slug}.png"
    image_url = url_for('static', filename=image_filename)

    # Load forecast series for inline chart (future only)
    forecast_csv_path = os.path.join('Prototype', 'forecast_data', f'forecast_{warehouse_slug}.csv')
    chart_labels = []
    chart_values = []
    try:
        df_fore = pd.read_csv(forecast_csv_path)
        # Expect columns: ds, yhat, trend, weekly, diwali
        chart_labels = [str(d) for d in df_fore['ds'].tolist()]
        chart_values = [float(v) for v in df_fore['yhat'].tolist()]
    except Exception:
        chart_labels = []
        chart_values = []

    # Prepare simple lists of upcoming events for details
    under_list = sorted(data.get('understock_info', []), key=lambda x: x.get('date', '9999-12-31'))[:5]
    over_list = sorted(data.get('overstock_info', []), key=lambda x: x.get('date', '9999-12-31'))[:5]

    # Compute upcoming "perfect" days (within limits)
    perfect_list = []
    first_perfect = None
    try:
        if under_threshold is not None and over_threshold is not None and 'ds' in df_fore.columns and 'yhat' in df_fore.columns:
            for _, r in df_fore.sort_values('ds').iterrows():
                try:
                    y = float(r['yhat'])
                    if (y >= float(under_threshold)) and (y <= float(over_threshold)):
                        date_str = str(r['ds'])
                        perfect_list.append({'date': date_str, 'forecasted_stock': y})
                        if first_perfect is None:
                            first_perfect = {'date': date_str, 'forecasted_stock': y}
                except Exception:
                    continue
            perfect_list = perfect_list[:5]
    except Exception:
        perfect_list = []
        first_perfect = None

    ist = pytz.timezone('Asia/Kolkata')
    timestamp = datetime.now(ist).strftime('%Y-%m-%d %I:%M %p IST')

    return render_template(
        'warehouse.html',
        warehouse_name=warehouse_name,
        next_under=next_under,
        next_over=next_over,
        thresholds={'under': under_threshold, 'over': over_threshold},
        summary=row,
        image_url=image_url,
        timestamp=timestamp,
        chart_labels=chart_labels,
        chart_values=chart_values,
        under_list=under_list,
        over_list=over_list,
        perfect_list=perfect_list,
        first_perfect=first_perfect
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5050)