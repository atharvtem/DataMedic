# Optional synthetic files to try

Upload sales.csv and customers.csv together. They contain invented data only.
Try: “Find missing customer IDs, repeated sale IDs, and customer IDs not in the customer file. Show total sales by month.”

Expected review signals: sale S5 has a blank customer ID; C9 has no reference row; S8 repeats. Monthly totals, including the repeated row as it exists in the input, are January 300, February 400, March 5700. No input records should be removed or changed. Unusual amounts are only candidates for review; the data does not prove whether 5000 is incorrect.

