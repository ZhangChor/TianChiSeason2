from models.graph import Graph
from models.handing import FlightData
from pickle import dumps, loads


def deep_copy(data):
    return loads(dumps(data))  # 代替copy.deepcopy


class ColumnGeneration(object):
    def __init__(self, graph: Graph):
        self.graph: Graph = graph
        self.flight_data: FlightData = graph.flight_data
        self.graph_node_copy = deep_copy(self.flight_data.graph_node_list)  # 可以用到的时候再复制

