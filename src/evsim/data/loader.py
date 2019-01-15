#!/usr/bin/env python

import logging
import os
import pandas as pd
from pathlib import Path

from evsim.data import balancing, car2go, intraday

logger = logging.getLogger(__name__)

PROJECT_DIR = str(Path(__file__).resolve().parents[3])
CAR2GO_PATH = PROJECT_DIR + "/data/raw/car2go/"
PROCESSED_DATA_PATH = PROJECT_DIR + "/data/processed/"
PROCESSED_TRIPS_FILE = PROCESSED_DATA_PATH + "/trips.pkl"
PROCESSED_CAPACITY_FILE = PROCESSED_DATA_PATH + "/capacity.pkl"
CAR2GO_FILES = [
    # "stuttgart.2016.03.22-2016.11.30.csv",
    "stuttgart.2016.12.01-2017.02.22.csv",
    "stuttgart.2017.02.23-2017-05-01.csv",
    # "stuttgart.2017.05.01-2017.10.31.csv",
    # "stuttgart.2017.11.01-2018.01.31.csv",
]

ACTIVATED_CONTROL_RESERVE_FILE = (
    PROJECT_DIR + "/data/raw/balancing/activated_control_reserve_2016_2017.csv"
)
TENDER_RESULTS_FILE = PROJECT_DIR + "/data/raw/balancing/tender_results_2016_2017.csv"

PROCOM_TRADES_FILE = PROJECT_DIR + "/data/raw/intraday/procom_data.csv"

PROCESSED_CONTROL_RESERVE_FILE = PROCESSED_DATA_PATH + "/activated_control_reserve.csv"
PROCESSED_TENDER_RESULTS_FILE = PROCESSED_DATA_PATH + "/tender_results.csv"
PROCESSED_BALANCING_PRICES_FILE = PROCESSED_DATA_PATH + "/balancing_prices.csv"
PROCESSED_INTRADAY_PRICES_FILE = PROCESSED_DATA_PATH + "/intraday_prices.csv"


def main():
    # Log to console
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%d.%m. %H:%M:%S",
        handlers=[logging.StreamHandler()],
    )

    print(load_car2go_trips(rebuild=True))
    print(load_car2go_capacity(rebuild=True))
    print(load_balancing_data(rebuild=True))
    print(load_intraday_prices(rebuild=True))


def load_car2go_trips(rebuild=False):
    """Loads processed trip data into a dataframe, process again if needed"""

    # Return early if processed files is present
    if rebuild is False and os.path.isfile(PROCESSED_TRIPS_FILE):
        return pd.read_pickle(PROCESSED_TRIPS_FILE)

    if not os.path.exists(PROCESSED_DATA_PATH):
        os.makedirs(PROCESSED_DATA_PATH)

    files = []
    for f in CAR2GO_FILES:
        logger.info("Reading %s..." % f)
        files.append(pd.read_csv(CAR2GO_PATH + f))
    df = pd.concat(files)

    df_trips = car2go.process(df)
    df_trips = (
        df_trips.sort_values(["start_time"]).reset_index().drop(["index"], axis=1)
    )
    df_trips.to_csv(PROCESSED_TRIPS_FILE.strip(".pkl") + ".csv")
    pd.to_pickle(df_trips, PROCESSED_TRIPS_FILE)
    logger.info("Wrote all processed trips files to %s" % PROCESSED_TRIPS_FILE)

    return pd.read_pickle(PROCESSED_TRIPS_FILE)


def load_car2go_capacity(rebuild=False):
    """Loads processed capacity data into a dataframe, process again if needed"""
    df_trips = load_car2go_trips()

    if rebuild is False and os.path.isfile(PROCESSED_CAPACITY_FILE):
        return pd.read_pickle(PROCESSED_CAPACITY_FILE)

    logger.info("Processing %s..." % PROCESSED_CAPACITY_FILE)
    df = car2go.calculate_capacity(df_trips)
    df.to_csv(PROCESSED_CAPACITY_FILE.strip(".pkl") + ".csv")
    pd.to_pickle(df, PROCESSED_CAPACITY_FILE)
    logger.info("Wrote calculated car2go demand to %s" % PROCESSED_CAPACITY_FILE)
    return pd.read_pickle(PROCESSED_CAPACITY_FILE)


def load_intraday_prices(rebuild=False):
    """Loads intraday prices, calculate again if needed"""

    if rebuild is False and os.path.isfile(PROCESSED_INTRADAY_PRICES_FILE):
        return pd.read_csv(PROCESSED_INTRADAY_PRICES_FILE)
    else:
        df = pd.read_csv(
            PROCOM_TRADES_FILE,
            sep=",",
            index_col=False,
            dayfirst=True,
            parse_dates=[1, 9],
            infer_datetime_format=True,
        )
        df[df["product"] == "H"].to_pickle(PROCESSED_DATA_PATH + "/procom_H.pkl")
        df[df["product"] == "Q"].to_pickle(PROCESSED_DATA_PATH + "/procom_Q.pkl")
        df[df["product"] == "B"].to_pickle(PROCESSED_DATA_PATH + "/procom_B.pkl")

        df_q = pd.read_pickle(PROCESSED_DATA_PATH + "/procom_Q.pkl")

        df_q = intraday.calculate_clearing_prices(df_q)
        df_q.to_csv(PROCESSED_INTRADAY_PRICES_FILE, index=True)
        logger.info(
            "Wrote calculated intraday clearing prices to %s"
            % PROCESSED_INTRADAY_PRICES_FILE
        )
        return df_q


def load_balancing_data(rebuild=False):
    """Loads processed balancing data into a dataframe, process again if needed"""

    if rebuild is False and os.path.isfile(PROCESSED_TENDER_RESULTS_FILE):
        df_results = pd.read_csv(PROCESSED_TENDER_RESULTS_FILE)
    else:
        df_results = pd.read_csv(
            TENDER_RESULTS_FILE,
            sep=";",
            decimal=",",
            dayfirst=True,
            parse_dates=[0, 1],
            infer_datetime_format=True,
        )

        df_results = balancing.process_tender_results(df_results)
        df_results.to_csv(PROCESSED_TENDER_RESULTS_FILE, index=False)
        logger.info(
            "Wrote processed tender results to %s" % PROCESSED_TENDER_RESULTS_FILE
        )

    if rebuild is False and os.path.isfile(PROCESSED_CONTROL_RESERVE_FILE):
        df_activated_srl = pd.read_csv(PROCESSED_CONTROL_RESERVE_FILE)
    else:
        df_activated_srl = pd.read_csv(
            ACTIVATED_CONTROL_RESERVE_FILE,
            sep=";",
            decimal=",",
            thousands=".",
            dayfirst=True,
            parse_dates=[0],
            infer_datetime_format=True,
        )

        df_activated_srl = balancing.process_activated_reserve(df_activated_srl)
        df_activated_srl.to_csv(PROCESSED_CONTROL_RESERVE_FILE, index=False)
        logger.info(
            "Wrote processed activated control reserve to %s"
            % PROCESSED_CONTROL_RESERVE_FILE
        )

    if rebuild is False and os.path.isfile(PROCESSED_BALANCING_PRICES_FILE):
        return pd.read_csv(
            PROCESSED_BALANCING_PRICES_FILE,
            parse_dates=[0, 1],
            infer_datetime_format=True,
        )
    else:
        df = balancing.calculate_clearing_prices(df_results, df_activated_srl)
        df.to_csv(PROCESSED_BALANCING_PRICES_FILE, index=False)
        logger.info(
            "Wrote processed balancing clearing prices to %s"
            % PROCESSED_BALANCING_PRICES_FILE
        )

    return df


if __name__ == "__main__":
    main()