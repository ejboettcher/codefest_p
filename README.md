# Vehicle Cost Estimator
 
A Streamlit app for building a list of vehicles by type, quantity and unit cost, then comparing the totals against the spread of costs in an uploaded dataset.
 
## Getting started
 
1. Install the dependencies: `pip install -r requirements.txt`
2. Start the app: `streamlit run app.py`
3. Upload `sample_vehicle_costs.csv` (125 vehicles across 5 types) to try it out, or use your own file.
## The sidebar
 
### Uploading a dataset
 
You start by uploading a CSV or Excel file. The file needs one column that holds the vehicle type and one numeric column that holds the cost. The app guesses which columns these are by looking for names like "type", "category" or "class" for the type, and "cost", "price" or "amount" for the cost. If it guesses wrong, open **Dataset columns** in the sidebar and pick the right ones.
 
Type names are matched regardless of capitalization or extra spaces, so "suv" in your file matches "SUV" in the dropdown.
 
### Adding line items
 
Below the upload area are three collapsible sections: Group 1, Group 2 and Group 3. Each one has a **Type** dropdown. Its options come from your dataset, or default to SUV, Compact and Full Size if you haven't uploaded one.
 
Each section also has **Quantity** and **Unit cost** boxes. The cost fills in with the dataset's average for the chosen type, and a small note shows that average and its standard deviation. You can overwrite the cost with your own number.
 
Clicking **Add row** adds a row to an editable table right below the button. In that table you can change the type, quantity or cost of any row, add new rows, or delete rows.
 
### Managing groups
 
Each group has a **Clear rows** button that empties its table and a **Remove group** button that deletes the whole section (available as long as more than one group exists). The **➕ Add group** button at the bottom of the sidebar adds another section.
 
## The main panel
 
### Totals at the top
 
The top row shows the total cost of all line items, the number of units, the number of line items, and the **Total σ** (explained below).
 
### Totals by type
 
This table lists, for each type, the units, total cost, and your average entered cost next to the dataset's mean, standard deviation and record count for that type. Every type in the dataset appears, even ones you haven't entered yet, so you can see the cost spread for all types at a glance.
 
If you enter a type that isn't in the dataset, or that has only one cost record, the app shows a warning that no standard deviation is available for it.
 
### Chart
 
A bar chart shows the total cost by type, with whiskers showing ± one standard deviation of each type's total. Hovering over a bar shows its units, total cost and standard deviation.
 
### Expandable sections
 
**All line items** lists every row from every group, with its line total (quantity × unit cost), and includes a button to download them as a CSV. **Dataset cost statistics** shows the record count, mean, standard deviation, minimum and maximum cost for each type in the dataset.
 
## How the standard deviations are calculated
 
The **Dataset σ (per unit)** column is the sample standard deviation of cost for each type in your uploaded file. It describes how much the cost of a single vehicle of that type varies.
 
The **σ of total** column estimates how much each type's total could vary. It is calculated as σ × √units. For example, if SUVs have a σ of $5,000 and you enter 4 of them, the σ of the SUV total is $5,000 × √4 = $10,000.
 
The overall **Total σ** combines all types the same way: √Σ(units × σ²).
 
Both of these assume each vehicle's cost varies independently of the others. If you only want the plain standard deviation per type, you can remove the σ of total column and the Total σ metric from `app.py`.
 
## Files
 
`app.py` is the Streamlit app. `requirements.txt` lists the Python packages it needs (Streamlit 1.50 or newer, pandas, NumPy, Altair and openpyxl for Excel files). `sample_vehicle_costs.csv` is a sample dataset with `vehicle_id`, `vehicle_type` and `cost` columns.
 