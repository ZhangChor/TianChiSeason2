from models.handing import FlightData
from datetime import datetime, timedelta

min_turn_time = timedelta(minutes=50)
duration_start = datetime(year=2017, month=5, day=6, hour=6)
duration_end = datetime(year=2017, month=5, day=9, hour=0)

max_lead_time = timedelta(hours=6)
max_domestic_delay = timedelta(hours=24)
max_foreign_delay = timedelta(hours=36)


flight_data = FlightData(min_turn_time, duration_start, duration_end,
                         max_lead_time, max_domestic_delay, max_foreign_delay)
AIRCRAFT_NUM = 142
typhoon_list = [(49, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17)),
                (50, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17)),
                (61, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17))]
flight_data.add_typhoon(typhoon_list)
flight_data.selection_data(AIRCRAFT_NUM)

