import pandas as pd
import wrds

db = wrds.Connection(wrds_username="armaang06")
tickers = pd.read_csv("data/data_pulling/constituents.csv")["Symbol"].to_list()
names = db.raw_sql(f"""
    select permno, ticker, comnam, shrcd,exchcd, namedt, nameendt
    from crsp.stocknames
    where ticker in {tickers}
    order by ticker, namedt 

""")


