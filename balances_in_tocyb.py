# %%
import datetime
from time import time

import pandas as pd
from IPython.core.display import HTML, display

from config import BOSTROM_NODE_URL, IBC_COIN_NAMES
from src.bash_utils import get_json_from_bash_query

# %%
BOSTROM_NODE_URL = "https://rpc.bostrom.cybernode.ai:443"
BOSTROM_POOLS_BASH_QUERY = (
    f"cyber query liquidity pools --node {BOSTROM_NODE_URL} -o json"
)

ADDRESSES_DICT = {
    # "bostrom1s4czxghmh29aw2ldynk8r9lnkfccw5ph8rjpxa": "1",
    # "bostrom1dxpm2ne0jflzr2hy9j5has6u2dvfv68calunqy": "2",
    "bostrom1nngr5aj3gcvphlhnvtqth8k3sl4asq3n6r76m8": "3",
}

TOKENS_TO_CONVERT = {
    "millivolt": "VOLT",
    "milliampere": "AMPERE",
    "uosmo in bostrom": "OSMO",
    "uatom in bostrom": "ATOM",
}  # tokens to divide by 1000


def rename_denom(denom: str, ibc_coin_names: dict = IBC_COIN_NAMES) -> str:
    return ibc_coin_names[denom] if denom in ibc_coin_names.keys() else denom


_time_of_update = datetime.datetime.now()  # Time to mark all dfs

# %%

supply_bostrom_df = (
    pd.DataFrame.from_records(
        get_json_from_bash_query(
            "cyber query bank total --chain-id bostrom --node https://rpc.bostrom.cybernode.ai:443 -o json"
        )["supply"]
    )
    .set_index("denom")
    .rename(columns={"amount": "pool_tokens_amount"})
    .astype("int64")
)

# %%
pools_df = (
    pd.DataFrame.from_records(
        get_json_from_bash_query(
            "cyber query liquidity pools  --chain-id bostrom --node https://rpc.bostrom.cybernode.ai:443 -o json"
        )["pools"]
    )
    .set_index("pool_coin_denom")
    .drop(columns=["id", "type_id"])
)


# %%
pools_df["balances"] = pools_df["reserve_account_address"].map(
    lambda address: get_json_from_bash_query(
        f"cyber query bank balances {address} --chain-id bostrom --node https://rpc.bostrom.cybernode.ai:443  -o json"
    )["balances"]
)

pools_df["coin_1_amount"] = (
    pools_df["balances"].apply(lambda x: x[0]["amount"]).astype("int64")
)
pools_df["coin_2_amount"] = (
    pools_df["balances"].apply(lambda x: x[1]["amount"]).astype("int64")
)

pools_df[["coin_1", "coin_2"]] = pools_df["reserve_coin_denoms"].apply(
    lambda x: pd.Series([x[0], x[1]])
)

pools_df = pd.DataFrame.merge(
    pools_df,
    supply_bostrom_df,
    left_index=True,
    right_index=True,
)

# %%
# here we calculate prices on tokens in H and TOCYB
df_temp = pools_df[["coin_1", "coin_1_amount", "coin_2", "coin_2_amount"]]

df_temp_reverse = df_temp.copy()
df_temp_reverse.columns = ["coin_2", "coin_2_amount", "coin_1", "coin_1_amount"]

prices_df = pd.concat(
    [
        df_temp,
        df_temp_reverse,
        pd.DataFrame.from_dict(
            {
                "coin_1": ["hydrogen"],
                "coin_2": ["hydrogen"],
                "coin_1_amount": [1],
                "coin_2_amount": [1],
            }
        ),
    ]
)
prices_df = prices_df[prices_df["coin_2"] == "hydrogen"]
prices_df = prices_df.set_index("coin_1")
prices_df = prices_df[["coin_1_amount", "coin_2_amount"]]


prices_df["price_in_h"] = prices_df["coin_2_amount"] / prices_df["coin_1_amount"]
h_in_tocyb = prices_df.at["tocyb", "price_in_h"]

prices_df["price_in_tocyb"] = prices_df["price_in_h"] / h_in_tocyb  # type: ignore
prices_df.drop(columns=["coin_1_amount", "coin_2_amount", "price_in_h"], inplace=True)


# %%
def get_delegations(address: str):
    delegations = pd.DataFrame.from_records(
        get_json_from_bash_query(
            f"cyber query staking delegations {address} --chain-id bostrom --node https://rpc.bostrom.cybernode.ai:443 -o json"
        )["delegation_responses"]
    )
    boots_delegated = (
        delegations["balance"].map(lambda x: x["amount"]).astype("int64").sum()
    )
    row = pd.DataFrame(
        {
            "denom": ["boot"],
            "amount": [boots_delegated],
            "address": [address],
            "state": ["delegated"],
        }
    )

    return row


delegated_df = pd.concat(
    [get_delegations(address) for address in ADDRESSES_DICT.keys()]
)


# %%
def get_rewards(address: str):
    rewards = get_json_from_bash_query(
        f"cyber query distribution rewards {address} --chain-id bostrom --node https://rpc.bostrom.cybernode.ai:443 -o json"
    )["total"]
    rewards_df = pd.DataFrame.from_records(rewards)
    rewards_df["amount"] = rewards_df["amount"].astype("float_").astype("int64")
    rewards_df["address"] = address

    rewards_df = rewards_df[rewards_df["amount"] != 0]

    return rewards_df


rewards_df = pd.concat([get_rewards(address) for address in ADDRESSES_DICT.keys()])

rewards_pools_df = rewards_df[rewards_df["denom"].str.startswith("pool")].set_index(
    "denom"
)
rewards_pools_df["state"] = "pool-rewards"

rewards_staking_df = rewards_df[~rewards_df["denom"].str.startswith("pool")]

rewards_staking_df["state"] = "rewards"


def get_balance(address: str):
    balance = get_json_from_bash_query(
        f"cyber query bank balances {address} --chain-id bostrom --node https://rpc.bostrom.cybernode.ai:443 -o json"
    )["balances"]
    balance_df = pd.DataFrame.from_records(balance)
    balance_df["amount"] = balance_df["amount"].astype("int64")
    balance_df["address"] = address
    balance_df.set_index("denom", inplace=True)

    return balance_df


balance_df = pd.concat([get_balance(address) for address in ADDRESSES_DICT.keys()])

# %%
pool_tokens = balance_df.loc[balance_df.index.str.startswith("pool")]
pool_tokens["state"] = "pool"

pool_tokens = pd.concat([pool_tokens, rewards_pools_df])

pool_tokens = pool_tokens.join(pools_df)
# %%
pool_tokens["coin_1_amount_to_withdraw"] = (
    pool_tokens["amount"]
    / pool_tokens["pool_tokens_amount"]
    * pool_tokens["coin_1_amount"]
)
pool_tokens["coin_2_amount_to_withdraw"] = (
    pool_tokens["amount"]
    / pool_tokens["pool_tokens_amount"]
    * pool_tokens["coin_2_amount"]
)


# %%
def pool_tokens_pivot_longer(pool_tokens):
    df1 = pool_tokens[["coin_1", "coin_1_amount_to_withdraw", "address", "state"]]
    df1.columns = ["denom", "amount", "address", "state"]
    df2 = pool_tokens[["coin_2", "coin_2_amount_to_withdraw", "address", "state"]]
    df2.columns = ["denom", "amount", "address", "state"]

    tokens_in_pools_df = pd.concat([df1, df2]).reset_index(drop=True)
    return tokens_in_pools_df


tokens_in_pools_df = pool_tokens_pivot_longer(pool_tokens)

# %%
non_pool_df = balance_df.loc[~balance_df.index.str.startswith("pool")].reset_index()


# %%
def get_investminted_tokens(address: str):
    json = get_json_from_bash_query(
        f"cyber query account {address} --chain-id bostrom --node https://rpc.bostrom.cybernode.ai:443 -o json"
    )

    ep = datetime.datetime(1970, 1, 1, 0, 0, 0)
    current_time = (datetime.datetime.utcnow() - ep).total_seconds()

    slot_time = int(json["start_time"])
    slots = []

    for i in json["vesting_periods"]:
        slot_time = int(i["length"]) + slot_time
        if slot_time > current_time:
            slots.extend(i["amount"])

    df = pd.DataFrame(slots)
    df["amount"] = df["amount"].astype("int64")

    df = df.groupby("denom").sum()
    df = df.reset_index()

    df["address"] = address
    df["state"] = "investminted"

    return df


investminted_df = pd.concat(
    [get_investminted_tokens(address) for address in ADDRESSES_DICT.keys()]
)


# %%
liquid_df = pd.merge(
    non_pool_df,
    investminted_df,
    left_on=["denom", "address"],
    right_on=["denom", "address"],
    how="left",
).fillna(0)

liquid_df["amount"] = liquid_df["amount_x"] - liquid_df["amount_y"]
liquid_df = liquid_df[["denom", "address", "amount"]]
liquid_df["state"] = "liquid"

# %%
total_df = pd.concat(
    [
        tokens_in_pools_df,
        liquid_df,
        delegated_df,
        investminted_df,
        rewards_staking_df,
    ]
)

total_df = pd.merge(total_df, prices_df, left_on="denom", how="left", right_index=True)
total_df["amount_in_tocyb"] = total_df["price_in_tocyb"] * total_df["amount"]

total_df.drop(columns="price_in_tocyb", inplace=True)

total_df["address_label"] = total_df["address"].map(ADDRESSES_DICT)

total_df = total_df.sort_values(["address_label", "amount_in_tocyb"], ascending=False)

total_df["denom"] = total_df["denom"].map(lambda x: rename_denom(x))

total_df["denom"] = total_df["denom"].replace(TOKENS_TO_CONVERT)
total_df["denom"] = total_df["denom"].str.upper()

total_df["amount"].where(
    ~total_df["denom"].isin(["OSMO", "ATOM"]),
    total_df["amount"] / 1000000,
    inplace=True,
)

total_df["amount"].where(
    ~total_df["denom"].isin(["AMPERE", "VOLT"]),
    total_df["amount"] / 1000,
    inplace=True,
)

total_df = total_df[
    ["address_label", "denom", "state", "amount", "amount_in_tocyb", "address"]
]
# total_df.to_clipboard()

pd.set_option("display.max_colwidth", None)
pd.options.display.float_format = "{0:7,.0f}".format
display(HTML(total_df.to_html(index=False, notebook=True, show_dimensions=False)))

# %%
