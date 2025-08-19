import pandas as pd
import numpy as np
from datetime import timedelta

# Define warehouse details from the sample
warehouses = [
    ("WH001", "Bawana Main", 50, 40, 12),
    ("WH002", "Okhla Depot", 45, 35, 10),
    ("WH003", "Narela Hub", 55, 45, 14),
    ("WH004", "Mayapuri Store", 48, 38, 11),
    ("WH005", "Rohini Warehouse", 50, 40, 12),
    ("WH006", "Kirti Nagar Hub", 52, 42, 13),
    ("WH007", "Sarai Kale Khan Depot", 50, 40, 12)
]

# Date range
start_date = pd.to_datetime("2023-01-01")
end_date = pd.to_datetime("2024-12-31")
dates = pd.date_range(start=start_date, end=end_date, freq='D')

# Seasonal events (date, adjustment: positive for peaks, negative for troughs)
events = [
    ("2023-03-07", 250), ("2024-03-24", 250),  # Holi
    ("2023-06-15", -200), ("2024-06-20", -200),  # Monsoon Trough
    ("2023-08-30", 200), ("2024-08-15", 200),  # Raksha Bandhan
    ("2023-09-07", 150), ("2024-09-07", 150),  # Ganesh Chaturthi
    ("2023-10-28", 300), ("2024-10-31", 300),  # Diwali
    ("2023-12-15", -150), ("2024-12-20", -150),  # Post-Festival Trough
    ("2023-12-25", 200), ("2024-12-25", 200)   # Christmas
]

# Generate data
data = []
base_means = {
    "WH001": 900, "WH002": 700, "WH003": 1000, "WH004": 850,
    "WH005": 900, "WH006": 950, "WH007": 1000
}
for date in dates:
    base_stock_adjustment = 0
    for event_date, adj in events:
        if date.strftime("%Y-%m-%d") == event_date:
            base_stock_adjustment = adj
    for warehouse_id, warehouse_name, x_length_m, y_length_m, z_height_m in warehouses:
        mean_stock = base_means[warehouse_id]
        for i in range(20):  # 20 entries per day
            time = f"{(i * 3):02d}:{(i * 3 % 60):02d}"  # 3-minute increments for 20 entries
            base_stock = mean_stock + np.random.normal(0, 50)  # Baseline with noise
            stock = max(0, base_stock + base_stock_adjustment + np.random.uniform(-100, 100))
            loaded_unloaded = "loaded" if np.random.random() > 0.5 else "unloaded"
            data.append([date.strftime("%Y-%m-%d"), time, int(stock), loaded_unloaded, warehouse_id, warehouse_name, x_length_m, y_length_m, z_height_m])

df = pd.DataFrame(data, columns=["date", "time", "stock", "loaded_unloaded", "warehouse_id", "warehouse_name", "x_length_m", "y_length_m", "z_height_m"])
df.to_csv("Prototype/inventory_data_simulated.csv", index=False)