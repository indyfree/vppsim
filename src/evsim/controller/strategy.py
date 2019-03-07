from datetime import datetime, timedelta, time
import pandas as pd


def regular(env, controller, fleet, timestep):
    """ Charge all EVs at regular prices"""

    evs = controller.dispatch(
        fleet, criteria="battery.level", n=len(fleet) - 5, timestep=timestep
    )
    controller.log(env, "Charging %d EVs." % len(evs))
    controller.log(env, evs)

    for ev in evs:
        ev.action = env.process(ev.charge_timestep(timestep))


def balancing(env, controller, fleet, timestep):
    """ Charge predicted available EVs with balancing electricity
        charge others from regular electricity tariff"""

    # 1. Bid for every 15-minute slot of the next day at 16:00
    # NOTE: Look up exact balancing mechanism
    dt = datetime.fromtimestamp(env.now)
    if dt.time() == time(16, 0):
        tomorrow = dt.date() + timedelta(days=1)
        intervals = pd.date_range(
            start=tomorrow, end=tomorrow + timedelta(days=1), freq="15min"
        )[:-1]

        for i in intervals:
            try:
                ts = i.to_pydatetime().timestamp()
                _update_consumption_plan(
                    env,
                    controller,
                    controller.balancing,
                    ts,
                    controller.industry_tariff,
                )
            except ValueError as e:
                controller.error(env, "Could not update consumption plan: %s" % e)

    # 2. Charge from balancing if in consumption plan, regulary else
    _charge_consumption_plan(env, controller, fleet, timestep)


def intraday(env, controller, fleet, timestep):
    """ Charge predicted available EVs with intraday electricity
        charge others from regular electricity tariff"""

    # NOTE: Assumption: 30min ahead we can procure at price >= clearing price
    dt = datetime.fromtimestamp(env.now + (60 * 30))

    # 1. Bid for 15-min timeslots
    if dt.minute % 15 == 0:
        try:
            _update_consumption_plan(
                env,
                controller,
                controller.intraday,
                dt.timestamp(),
                controller.industry_tariff,
            )
        except ValueError as e:
            controller.error(env, "Could not update consumption plan: %s" % e)

    # 2. Charge from balancing if in consumption plan, regulary else
    _charge_consumption_plan(env, controller, fleet, timestep)


def _charge_consumption_plan(env, controller, fleet, timestep):
    # 2. Charge from intraday if in consumption plan
    # TODO Pass EV capacity as param or use number EVs
    consumption_evs = int(controller.get_consumption(env.now) // controller.ev_capacity)
    if consumption_evs > len(fleet):
        controller.error(
            env,
            "Overcommited %.2fkW capacity, account for imbalance costs!"
            % ((consumption_evs - len(fleet)) * controller.ev_capacity),
        )
        consumption_evs = len(fleet)

    try:
        controller.dispatch(
            env, fleet, criteria="battery.level", n=consumption_evs, timestep=timestep
        )
        controller.log(
            env,
            "Charging %d/%d EVs from intraday market." % (consumption_evs, len(fleet)),
        )
    except ValueError as e:
        controller.error(env, str(e))

    # 3. Charge remaining EVs regulary
    regular_evs = max(0, len(fleet) - consumption_evs)
    try:
        controller.dispatch(
            env,
            fleet,
            criteria="battery.level",
            n=regular_evs,
            descending=True,
            timestep=timestep,
        )
        controller.log(env, "Charging %d/%d EVs regulary." % (regular_evs, len(fleet)))
    except ValueError as e:
        controller.error(env, str(e))


def _update_consumption_plan(env, controller, market, timeslot, industry_tariff):
    """ Updates the consumption plan for a given timeslot (POSIX timestamp)
    """

    predicted_clearing_price = controller.predict_clearing_price(market, timeslot)
    if predicted_clearing_price > industry_tariff:
        controller.log(env, "The industry tariff is cheaper.")
        return None

    available_capacity = controller.predict_capacity(env, timeslot)
    if available_capacity == 0:
        controller.log(env, "No available capacity predicted.")
        return None

    # NOTE: Simple strategy to always bid at predicted clearing price
    bid = market.bid(timeslot, predicted_clearing_price, available_capacity)
    if bid is None:
        controller.log(env, "Bid unsuccessful")
        return
    elif bid[0] in controller.consumption_plan:
        raise ValueError(
            "%s was already in consumption plan" % datetime.fromtimestamp(bid[0])
        )
    else:
        controller.log(
            env,
            "Bought %.2f kW for %.2f EUR/MWh for 15-min timeslot %s"
            % (bid[1], bid[2], datetime.fromtimestamp(bid[0])),
        )

        # TODO: Better data structure to save 15 min consumption plan
        # TODO: Save prices
        # TODO: Check timestamp() utc??
        # Bought capacity will be for 3 * 5-min timeslots
        for t in [0, 5, 10]:
            time = bid[0] + (60 * t)
            controller.consumption_plan[time] = bid[1]
