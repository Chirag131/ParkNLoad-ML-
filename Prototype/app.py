from flask import Flask, render_template, send_file
import pandas as pd
import os
import schedule
import subprocess

app = Flask(__name__)

# Define the path to the forecast summary file
FORECAST_SUMMARY_PATH = os.path.join('Prototype', 'forecast_summary.csv')

@app.route('/')
def home():
    # Read the CSV file
    try:
        df = pd.read_csv(FORECAST_SUMMARY_PATH)
        # Convert DataFrame to HTML table
        table_html = df.to_html(classes='table table-striped', index=False)
        return render_template('index.html', table=table_html)
    except FileNotFoundError:
        return "Error: forecast_summary.csv not found. Please run the forecast script first.", 404
    except Exception as e:
        return f"Error loading forecast summary: {e}", 500

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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

def run_forecast():
    subprocess.run(['python', 'forecast_logic.py'])

schedule.every().day.at("05:00").do(run_forecast)  # Run daily at 5 AM IST
while True:
    schedule.run_pending()