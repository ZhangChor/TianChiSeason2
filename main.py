from models.handing import FlightData
from models.graph import Graph
from models.iterate import ColumnGeneration
from datetime import datetime, timedelta
from time import time as current_time
from models.cplex_solver import ShortestPath

if __name__ == '__main__':
    min_turn_time = timedelta(minutes=50)
    duration_start = datetime(year=2017, month=5, day=6, hour=6)
    duration_end = datetime(year=2017, month=5, day=9, hour=0)

    max_lead_time = timedelta(hours=6)
    max_domestic_delay = timedelta(hours=24)
    max_foreign_delay = timedelta(hours=36)

    split_time = timedelta(minutes=30)
    slot_capacity = 12

    flight_data = FlightData(min_turn_time, duration_start, duration_end,
                             max_lead_time, max_domestic_delay, max_foreign_delay,
                             split_time, slot_capacity)
    AIRCRAFT_NUM = 10
    typhoon_list = [(49, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17)),
                    (50, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17)),
                    (61, datetime(2017, 5, 6, 16), datetime(2017, 5, 7, 17))]
    flight_data.add_typhoon(typhoon_list)
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
    mega_graph.build_graph()
    t1 = current_time()
    print('构造时间', t1-t0)
    cg = ColumnGeneration(mega_graph)
    # for i in range(AIRCRAFT_NUM):
    t3 = current_time()
    glc = cg.pre_traversal(3)
    cg.topological_ordering(3, glc)
    acc_matrix = cg.generate_association_matrix(3)
    t4 = current_time()
    print('预遍历，拓扑排序和产生关联矩阵时间', t4-t3)
    sp = ShortestPath(cg.ass_matrix_list[3], cg.node_attr_list[3], cg.edge_cost_list[3], relaxation=False)
    sp.add_mutex_constraint(flight_data.advance_flight_node_nums, cg.graph_node_index_list[3])
    sp.solve()
    t5 = current_time()
    print('求解最短路径时间', t5-t4)
    sp.print_info()
    print('最优解', sp.optimal)
    print('是否整数解', sp.is_int())
    print(sum(sp.solution))

