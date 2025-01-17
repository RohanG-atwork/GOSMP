from data_cleaning import load_and_clean, clean
from questions import questions, calculate_risk_score, calculate_risk_category
import streamlit as st
from collections import defaultdict
import datetime
import math
from pypfopt import expected_returns
from pypfopt import risk_models
from pypfopt.efficient_frontier import EfficientFrontier
import numpy as np
import pandas as pd


def withoutOptimization(timed_df: pd.DataFrame):
    """
    This function calculates the portfolio variance, volatility, and annual return without optimization.
    timed_df: pd.DataFrame: The processed df with the date as the index and the stock prices as the columns.
    """

    # Show daily returns
    returns = timed_df.pct_change()
    returns.fillna(0, inplace=True)
    returns.replace([np.inf, -np.inf], 0, inplace=True)

    # Annualized covariance matrix
    # cov_matrix_annual = returns.cov()*252
    cov_matrix_annual = returns.cov()*246
    cov_matrix_annual.fillna(0, inplace=True)
    cov_matrix_annual

    # assign equal weights to each stock
    weights = np.full(timed_df.shape[1], 1 / timed_df.shape[1])

    # calculate the portfolio variance
    port_variance = np.dot(weights.T, np.dot(cov_matrix_annual, weights))

    # calculate the portfolio volatility aka standard deviation
    port_volatility = np.sqrt(port_variance)

    # calculate the annual portfolio return
    port_annual_return = np.sum(returns.mean() * weights) * 246

    # expected annual return, volatility, and variance
    percent_var = str(round(port_variance, 2) * 100) + '%'
    percent_vols = str(round(port_volatility, 2) * 100) + '%'
    percent_ret = str(round(port_annual_return, 2) * 100) + '%'

    return port_variance, port_volatility, port_annual_return, percent_var, percent_vols, percent_ret


def withOptimization(timed_df: pd.DataFrame, exp_ret_type: dict, cov_type: dict, weight_type: dict):
    """
    This function calculates the portfolio variance, volatility, and annual return with optimization.
    timed_df: pd.DataFrame: The processed df with the date as the index and the stock prices as the columns.
    exp_ret_type: dict: The expected return type to be used in the optimization.
    cov_type: dict: The covariance type to be used in the optimization.

    exp_ret_type: dict: The expected return type to be used in the optimization.
    1. mean: The mean historical return.
    dict = {"type": "mean", "frequency": number}
    2. ema: The exponential moving average return.
    dict = {"type": "ema", "log_returns": boolean}
    3. capm: The CAPM return.
    dict = {"type": "capm"}

    cov_type: dict: The covariance type to be used in the optimization.
    1. sample_cov: The sample covariance matrix.
    dict = {"type": "sample_cov"}
    2. exp_cov: The exponentially weighted covariance matrix.
    dict = {"type": "exp_cov"}
    3. shrinkage: The shrunk covariance matrix.
    dict = {"type": "shrinkage"}


    weight_type: dict: The type of weights to be used in the optimization.
    1. max_sharpe: The maximum Sharpe ratio weights.
    dict = {"type": "max_sharpe"}
    2. min_volatility: The minimum volatility weights.
    dict = {"type": "min_volatility"}
    3. efficient_risk: The efficient risk weights.
    dict = {"type": "efficient_risk", "target_volatility": number}
    4. efficient_return: The efficient return weights.
    dict = {"type": "efficient_return", "target_return": number}

    """

    mu = None
    if exp_ret_type["type"] == "mean":
        mu = expected_returns.mean_historical_return(
            timed_df, frequency=exp_ret_type["frequency"])

    elif exp_ret_type["type"] == "ema":
        mu = expected_returns.ema_historical_return(
            timed_df, log_returns=exp_ret_type["log_returns"])

    elif exp_ret_type["type"] == "capm":
        mu = expected_returns.capm_return(timed_df)

    mu.fillna(0, inplace=True)
    mu.replace(np.inf, 0.0, inplace=True)
    S = None
    if cov_type["type"] == "sample_cov":
        S = risk_models.sample_cov(timed_df)

    elif cov_type["type"] == "exp_cov":
        S = risk_models.exp_cov(timed_df)

    elif cov_type["type"] == "shrinkage":
        S = risk_models.CovarianceShrinkage(timed_df)

    S.fillna(0, inplace=True)
    S.replace(np.inf, 0.0, inplace=True)

    # Regularize the covariance matrix
    S_f = S + 1e-6 * np.eye(S.shape[0])

    # Optimize for the maximal Sharpe ratio
    ef = EfficientFrontier(mu, S_f, solver="ECOS")

    if weight_type["type"] == "max_sharpe":
        weights = ef.max_sharpe()
    elif weight_type["type"] == "min_volatility":
        weights = ef.min_volatility()
    elif weight_type["type"] == "efficient_risk":
        weights = ef.efficient_risk(
            target_volatility=weight_type["target_volatility"])
    elif weight_type["type"] == "efficient_return":
        weights = ef.efficient_return(
            target_return=weight_type["target_return"])

    # calculate the portfolio variance
    refined_weights = ef.clean_weights()

    # get the portfolio performance and prints it
    performance = ef.portfolio_performance(verbose=True)

    # allocate the weights to the stocks

    refined_weights = {key: value for key,
                       value in refined_weights.items() if value != 0.0}

    # Normalize the percentages
    total_weight = sum(refined_weights.values())
    refined_weights_percent = {
        key: (value / total_weight) * 100 for key, value in refined_weights.items()}
    assest = []
    weight = {}
    print("Count: ", len(refined_weights_percent))
    for key, value in refined_weights_percent.items():
        assest.append(key)
        weight[key] = value
        print(f"{key}: {value:.2f}%")

    return performance, assest, weight


# newTimeDf = timed_df[[i for i in weight.keys()]]


def DiscreteAllocation(timed_df, weight, investAmount, startDate):
    reminder = 0
    newWeights = {}
    for key, value in weight.items():
        allocatedPrice = value*investAmount*0.01
        # Use Start date in iloc
        units = math.floor(allocatedPrice / timed_df[key][startDate])
        print(units)
        rem: pd.Series = allocatedPrice - units * timed_df[key][startDate]
        print(rem)
        newWeights[key] = {"price": timed_df[key][startDate], "units": units, "allocated": (
            value*investAmount*0.01), "reminder": rem}
        reminder += rem

    return reminder, newWeights

# r, weights = DiscreteAllocation(newTimeDf, weight, 100000, start_date)


def BackTest(df, startDate, duration, weights):
    """
    duration: in days
    startDate: starting date string
    weights: weights dict 
    """
    window = 6  # month
    # start = datetime.datetime.strptime(startDate, "%Y-%m-%d")
    start = startDate
    end = start + datetime.timedelta(days=30*window)

    end_stop_date = start + datetime.timedelta(days=duration)
    x = defaultdict(dict)
    c = 1
    while end < end_stop_date:
        end = start + datetime.timedelta(days=30*window)
        temp = df.loc[start:end, :]

        # print(temp.iloc[-1,0])
        for i in weights.keys():
            x[i][c] = {
                "date_start": str(temp[i].iloc[0:].index[0])[:10],
                "date_end": str(temp[i].iloc[-1:].index[0])[:10],
                "date_start_price": temp[i].iloc[0],
                "date_end_price": temp[i].iloc[-1]
            }
        for key, values in x.items():
            st = values[c]["date_start_price"]
            en = values[c]["date_end_price"]

            st_price = st * weights[key]["units"]
            en_price = en * weights[key]["units"]
            pct_cng = (en_price - st_price)/st_price * 100
            values[c]["st_price"] = st_price
            values[c]["en_price"] = en_price

            values[c]["pct_change"] = pct_cng
        start = end
        c += 1

    return x, c-1


# window, total_windows = BackTest(newTimeDf, "2010-01-05", 3000, weights)
# print(window, total_windows)


def PercentChange(window, totalWindows):
    pctChange = []
    endDate = []
    for part in range(1, totalWindows+1):
        startPrice = endPrice = 0
        end = None
        for key, value in window.items():
            cycle = window[key].get(part)
            startPrice += cycle['st_price']
            endPrice += cycle['en_price']
            # print(part , cycle['date_end'])
            end = cycle['date_end']
        endDate.append(end)
        pctChange.append(((endPrice - startPrice)/startPrice * 100))
    return pctChange, endDate


# portfolioPercentChange, endDates = PercentChange(window, total_windows)
# portfolio = pd.DataFrame({
#     'Date': endDates,
#     'PctChange': portfolioPercentChange
# })


# # plt.plot(data=portfolio)
# ax = portfolio.plot(x="Date", y="PctChange", kind="scatter",
#                     figsize=[12, 6], style='b', rot=90)
# portfolio.plot(x="Date", y="PctChange", kind="line", ax=ax, style='b', rot=90)


def backtest_with_nifty(nifty_csv_file, invest_amount, start_date, num_days: int, timed_df: pd.DataFrame, weights: dict):

    newTimeDf = timed_df[[i for i in weights.keys()]]

    r, weights = DiscreteAllocation(
        newTimeDf, weights, invest_amount, start_date.strftime("%Y-%m-%d"))

    window, total_windows = BackTest(newTimeDf, start_date, num_days, weights)

    portfolioPercentChange, endDates = PercentChange(window, total_windows)

    # portfolio = pd.DataFrame({
    # 'Date': endDates,
    # 'PctChange': portfolioPercentChange
    # })

    nifty = pd.read_csv(nifty_csv_file)

    nifty['Date'] = pd.to_datetime(nifty['Date'])

    nifty.set_index('Date', inplace=True)

    # Drop columns where every entry is 0.0
    nifty = nifty.loc[:, (nifty != 0).any(axis=0)]

    # # # Use the column selection to drop columns where less than the threshold number of values are non-zero
    threshold = 0.70 * len(nifty)
    nifty = nifty.loc[:, (nifty != 0).sum() >= threshold]
    nifty = nifty.iloc[::-1]

    # rename Close to Nifty
    nifty = nifty.rename(columns={'Close': 'nifty'})

    # reverse the index
    nifty = nifty.iloc[::-1]

    r, weights = DiscreteAllocation(
        nifty, {"nifty": 100.0}, invest_amount, start_date.strftime("%Y-%m-%d"))

    win, total_ = BackTest(nifty, start_date, num_days, weights)

    niftyPercentChange, niftyendDates = PercentChange(win, total_)

    # nifty_portfolio = pd.DataFrame({
    #     'Date': niftyendDates,
    #     'niftyPctChange': niftyPercentChange
    # })

    # dats = pd.concat([portfolio, nifty_portfolio["niftyPctChange"]], axis=1)

    # instead of concat, you can create a df with the two columns
    dats = pd.DataFrame({
        'Date': endDates,
        'PctChange': portfolioPercentChange,
        'niftyPctChange': niftyPercentChange
    })

    #     plt.figure(figsize=(10, 5))

    # plt.plot(dats["Date"], dats["PctChange"], color="blue")
    # plt.plot(dats["Date"], dats["niftyPctChange"], color="red")
    # plt.xlabel("Date")
    # plt.ylabel("Portfolio%")
    # plt.xticks(rotation=90)
    # plt.title("Portfolio vs Nifty")
    # # add ledgend to the plot
    # plt.legend(["Portfolio", "Nifty"])
    # plt.tight_layout()

    return dats

