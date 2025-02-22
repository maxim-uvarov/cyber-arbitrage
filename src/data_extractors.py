import requests
import pandas as pd
import numpy as np
from math import isnan
from IPython.core.display import display, HTML

from src.bash_utils import get_json_from_bash_query
from config import (
    IBC_COIN_NAMES,
    BOSTROM_RELATED_OSMO_POOLS,
    BOSTROM_POOLS_BASH_QUERY,
    OSMO_POOLS_API_URL,
    BOSTROM_NODE_URL,
    POOL_FEE,
)


def rename_denom(denom: str, ibc_coin_names: dict = IBC_COIN_NAMES) -> str:
    return ibc_coin_names[denom] if denom in ibc_coin_names.keys() else denom


def get_pools_bostrom(
    display_data: bool = False,
    bostrom_pools_bash_query: str = BOSTROM_POOLS_BASH_QUERY,
    bostrom_node_url: str = BOSTROM_NODE_URL,
) -> pd.DataFrame:
    _pools_bostrom_json = get_json_from_bash_query(bostrom_pools_bash_query)
    _pools_bostrom_df = pd.DataFrame(_pools_bostrom_json["pools"])
    _pools_bostrom_df["balances"] = _pools_bostrom_df["reserve_account_address"].map(
        lambda address: get_json_from_bash_query(
            f"cyber query bank balances {address} --node {bostrom_node_url} -o json"
        )["balances"]
    )
    _pools_bostrom_df["balances"] = _pools_bostrom_df["balances"].map(
        lambda x: [
            {"denom": rename_denom(item["denom"]), "amount": item["amount"]}
            for item in x
        ]
    )
    _pools_bostrom_df["reserve_coin_denoms"] = _pools_bostrom_df[
        "reserve_coin_denoms"
    ].map(lambda x: [rename_denom(item) for item in x])
    _pools_bostrom_df["swap_fee"] = 0.003
    _pools_bostrom_df["network"] = "bostrom"
    if display_data:
        print("Bostrom Pools")
        display(
            HTML(
                _pools_bostrom_df.to_html(
                    index=False, notebook=True, show_dimensions=False
                )
            )
        )
    return _pools_bostrom_df


def get_pools_osmosis(
    display_data: bool = False,
    osmo_pools_api_url: str = OSMO_POOLS_API_URL,
    bostrom_related_osmo_pools: tuple = BOSTROM_RELATED_OSMO_POOLS,
) -> pd.DataFrame:
    _pools_osmosis_json = requests.get(osmo_pools_api_url).json()
    _pools_osmosis_df = pd.DataFrame(_pools_osmosis_json["pools"])
    _pools_osmosis_df["id"] = _pools_osmosis_df["id"].astype(int)
    _pools_osmosis_df["type_id"] = _pools_osmosis_df["@type"].map(
        lambda x: 1 if x == "/osmosis.gamm.v1beta1.Pool" else 0
    )
    _pools_osmosis_df["totalWeight"] = _pools_osmosis_df["totalWeight"].astype(int)
    _pools_osmosis_df["balances"] = _pools_osmosis_df["poolAssets"].map(
        lambda x: [item["token"] for item in x]
    )
    _pools_osmosis_df["balances"] = _pools_osmosis_df["balances"].map(
        lambda x: [
            {"denom": rename_denom(item["denom"]), "amount": item["amount"]}
            for item in x
        ]
    )
    _pools_osmosis_df["denoms_count"] = _pools_osmosis_df["poolAssets"].map(
        lambda x: len(x)
    )
    _pools_osmosis_df["swap_fee"] = _pools_osmosis_df["poolParams"].map(
        lambda x: float(x["swapFee"])
    )
    _pools_osmosis_df["reserve_coin_denoms"] = _pools_osmosis_df["poolAssets"].map(
        lambda x: [item["token"]["denom"] for item in x]
    )
    _pools_osmosis_df["reserve_coin_denoms"] = _pools_osmosis_df[
        "reserve_coin_denoms"
    ].map(lambda x: [rename_denom(item) for item in x])
    _pools_osmosis_df["network"] = "osmosis"
    if display_data:
        print("Osmosis Pools")
        display(
            HTML(
                _pools_osmosis_df[_pools_osmosis_df.id.isin(bostrom_related_osmo_pools)]
                .sort_values("totalWeight", ascending=False)
                .to_html(index=False, notebook=True, show_dimensions=False)
            )
        )
    return _pools_osmosis_df


def get_pools(
    display_data: bool = False,
    network=None,
    bostrom_related_osmo_pools: tuple = BOSTROM_RELATED_OSMO_POOLS,
) -> pd.DataFrame:
    if network is None:
        _pools_bostrom_df = get_pools_bostrom()[
            ["network", "id", "type_id", "balances", "reserve_coin_denoms", "swap_fee"]
        ]
        _pools_osmosis_df = get_pools_osmosis()[
            [
                "network",
                "id",
                "type_id",
                "balances",
                "swap_fee",
                "reserve_coin_denoms",
                "denoms_count",
            ]
        ]
        _pools_df = _pools_bostrom_df.append(
            _pools_osmosis_df[
                (_pools_osmosis_df.denoms_count == 2)
                & (_pools_osmosis_df.id.isin(bostrom_related_osmo_pools))
            ]
        )[["network", "id", "type_id", "balances", "swap_fee", "reserve_coin_denoms"]]
    elif network == "bostrom":
        _pools_df = get_pools_bostrom()[
            ["network", "id", "type_id", "balances", "swap_fee", "reserve_coin_denoms"]
        ]
    elif network == "osmosis":
        _pools_df = get_pools_osmosis()[
            ["network", "id", "type_id", "balances", "swap_fee", "reserve_coin_denoms"]
        ]
    else:
        print(f"`network` parameter must be equaled `` or `osmosis`")
        return pd.DataFrame(
            columns=[
                "network",
                "id",
                "type_id",
                "balances",
                "reserve_coin_denoms",
                "swap_fee",
            ]
        )
    if display_data:
        display(
            HTML(_pools_df.to_html(index=False, notebook=True, show_dimensions=False))
        )
    return _pools_df


def get_prices(pools_df: pd.DataFrame, display_data: bool = False) -> pd.DataFrame:
    _coins_list = list(pools_df["reserve_coin_denoms"])
    _coins_unique_set = set(np.concatenate(_coins_list).flat)
    _price_df = pd.DataFrame(columns=_coins_unique_set, index=_coins_unique_set)

    for _index, _pool_row in pools_df.iterrows():
        _coins_pair = _pool_row.reserve_coin_denoms
        _balances = {item["denom"]: int(item["amount"]) for item in _pool_row.balances}
        _price_df.loc[_coins_pair[0], _coins_pair[1]] = (
            _balances[_coins_pair[0]] / _balances[_coins_pair[1]] * (1 - POOL_FEE)
        )
        _price_df.loc[_coins_pair[1], _coins_pair[0]] = (
            _balances[_coins_pair[1]] / _balances[_coins_pair[0]] * (1 - POOL_FEE)
        )
    for _coin in _coins_unique_set:
        _price_df.loc[_coin, _coin] = 1
    _price_df.loc["uatom in bostrom", "uatom in osmosis"] = 1
    _price_df.loc["uatom in osmosis", "uatom in bostrom"] = 1
    _price_df.loc["uosmo", "uosmo in bostrom"] = 1
    _price_df.loc["uosmo in bostrom", "uosmo"] = 1
    _price_df.loc["boot", "boot in osmosis"] = 1
    _price_df.loc["boot in osmosis", "boot"] = 1
    if display_data:
        display(HTML(_price_df.to_html(notebook=True, show_dimensions=False)))
    return _price_df


def get_price_enriched(
    price_df: pd.DataFrame, display_data: bool = False
) -> pd.DataFrame:
    _price_enriched_df = price_df.copy()
    for _col in [
        ["boot", "boot in osmosis"],
        ["uosmo", "uosmo in bostrom"],
        ["uatom in osmosis", "uatom in bostrom"],
    ]:
        for _index in _price_enriched_df.index:
            if isnan(_price_enriched_df.loc[_index, _col[0]]):
                _price_enriched_df.loc[_index, _col[0]] = _price_enriched_df.loc[
                    _index, _col[1]
                ]
                _price_enriched_df.loc[_col[0], _index] = _price_enriched_df.loc[
                    _col[1], _index
                ]
            elif isnan(_price_enriched_df.loc[_index, _col[1]]):
                _price_enriched_df.loc[_index, _col[1]] = _price_enriched_df.loc[
                    _index, _col[0]
                ]
                _price_enriched_df.loc[_col[1], _index] = _price_enriched_df.loc[
                    _col[0], _index
                ]
    _price_enriched_df.drop(
        columns=["uatom in bostrom", "uosmo in bostrom", "boot in osmosis"],
        index=["uatom in bostrom", "uosmo in bostrom", "boot in osmosis"],
    ).rename(columns={"uatom in osmosis": "uatom"}, index={"uatom in osmosis": "uatom"})
    if display_data:
        display(HTML(_price_enriched_df.to_html(notebook=True, show_dimensions=False)))
    return _price_enriched_df
