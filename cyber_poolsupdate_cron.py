# %%
import pandas as pd

from src.data_extractors import get_pools, get_prices

import os, requests
import datetime


def cyber_pools_update():
    path = "/Users/user/Documents/local_files/cyber_files/"
    os.chdir(path)
    pools_df = get_pools()

    _list = pools_df["balances"].to_list()
    _t = []
    for i in _list:
        _t.append([i[0]["denom"], i[0]["amount"], i[1]["denom"], i[1]["amount"]])

    _pools = pd.DataFrame.from_records(
        _t,
        columns=["Coin 1", "Coin 1 pool amount", "Coin 2", "Coin 2 pool amount"],
    )

    _pools["update_time"] = datetime.datetime.now()

    _pools.to_csv("csv/pools_log.csv", mode="a", index=False, header=False)
    print("Pools updated")


url = "https://gateway.ipfs.cybernode.ai/ipfs/"
timeout = 5
try:
    request = requests.get(url, timeout=timeout)
    cyber_pools_update()
except (requests.ConnectionError, requests.Timeout) as exception:
    print("No internet connection.")
