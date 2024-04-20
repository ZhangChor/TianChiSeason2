#!/home/zc/miniconda3/envs/cplex_acd/bin/python
import sys

from datetime import datetime, timedelta
from time import time as current_time

from models.handing import FlightData
from models.graph import Graph
from models.iterate import ColumnGeneration
from models.comparison import MimCostFlowProblem

sys.path.append(r'/home/zc/TianChiSeason2')

if __name__ == '__main__':
    workspace_path = r"D:/workspace/TianChiSeason2"
    # workspace_path = r"/home/zc/TianChiSeason2"
    min_turn_time = timedelta(minutes=50)
    duration_start = datetime(year=2017, month=5, day=6, hour=6)
    duration_end = datetime(year=2017, month=5, day=9, hour=0)

    max_lead_time = timedelta(hours=6)
    max_domestic_delay = timedelta(hours=24)
    max_foreign_delay = timedelta(hours=36)

    split_time = timedelta(minutes=60)
    slot_capacity = 24

    flight_data = FlightData(min_turn_time, duration_start, duration_end,
                             max_lead_time, max_domestic_delay, max_foreign_delay,
                             split_time, slot_capacity, workspace_path)
    AIRCRAFT_NUM = 25
    typhoon_list = [(49, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17)),
                    (50, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17)),
                    (61, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17))]
    flight_data.add_typhoon(typhoon_list)
    start_time = datetime(year=2017, month=5, day=6, hour=0)
    end_time = datetime(year=2017, month=5, day=8, hour=0)
    flight_data.selection_data(AIRCRAFT_NUM)
    mega_graph = Graph(flight_data)
    close_list = [(5, timedelta(hours=0, minutes=1), timedelta(hours=6, minutes=30),
                   datetime(year=2014, month=1, day=1), datetime(year=2017, month=12, day=31)),
                  (6, timedelta(hours=0, minutes=0), timedelta(hours=6, minutes=0),
                   datetime(year=2014, month=1, day=1), datetime(year=2017, month=12, day=31)),
                  (6, timedelta(hours=23, minutes=0), timedelta(hours=23, minutes=59),
                   datetime(year=2014, month=1, day=1), datetime(year=2017, month=12, day=31)),
                  (22, timedelta(hours=11, minutes=15), timedelta(hours=11, minutes=45),
                   datetime(year=2017, month=5, day=4), datetime(year=2017, month=5, day=7)),
                  (49, timedelta(hours=0, minutes=10), timedelta(hours=6, minutes=10),
                   datetime(year=2017, month=4, day=28), datetime(year=2017, month=6, day=1)),
                  (76, timedelta(hours=1, minutes=0), timedelta(hours=7, minutes=0),
                   datetime(year=2017, month=4, day=28), datetime(year=2017, month=7, day=9))]
    mega_graph.add_close(close_list)
    t0 = current_time()
    mega_graph.build_graph_v2()
    # mega_graph.build_graph()
    # mega_graph.save_graph_node_list()
    t1 = current_time()
    print('构造图时间', t1 - t0)
    cg = ColumnGeneration(mega_graph)
    airport_parking_constraint_list = [(49, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17), 2),
                                       (50, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17), 2),
                                       (61, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17), 0),
                                       (25, datetime(2017, 5, 7, 4), datetime(2017, 5, 7, 6), 11),
                                       (57, datetime(2017, 5, 7, 4), datetime(2017, 5, 7, 6), 7)]
    cg.add_airport_parking(airport_parking_constraint_list)
    cg.run(parallel=True)
    t2 = current_time()
    print(f"列生成运行时间：{t2 - t1}")
    print(f"子问题求解时间：{cg.subproblem_running_time}")
    # 对比实验，多商品流模型
    # mfm = MimCostFlowProblem(mega_graph)
    # mfm.add_airport_parking(airport_parking_constraint_list)
    # mfm.run(relation=True)
    # t3 = current_time()
    # print(f"商品流运行时间：{t3 - t2}")
    # print(f"总运行时间：{t3 - t0}")
    # mfm.print_route()
    from models.img_plt import line_plt
    line_plt(cg)
