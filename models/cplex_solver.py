#!/home/zc/miniconda3/envs/cplex_acd/bin/python
import sys

sys.path.append(r'/home/zc/PathModel3')
from docplex.mp.model import Model


class CplexSolver(object):
    def __init__(self, route: list, cost: list, var_num_list: list, cancel: list, relaxation=True):
        self._flight_node_num = len(cancel)
        self._aircraft_num = len(var_num_list)
        self._route_num = sum(var_num_list)
        self._var_name_list_x = []
        self.result = None

        j = 0
        for n in var_num_list:
            for i in range(n):
                self._var_name_list_x.append(f'c{j}r{i}')
            j += 1
        self._var_name_list_y = [f'n{i}' for i in range(self._flight_node_num)]
        self._solver = Model(name="route assignment problem")
        if relaxation:
            self._x_list = self._solver.continuous_var_list(self._var_name_list_x, name='x')
            self._y_list = self._solver.continuous_var_list(self._var_name_list_y, name='y')
        else:
            self._x_list = self._solver.binary_var_list(self._var_name_list_x, name='x')
            self._y_list = self._solver.binary_var_list(self._var_name_list_y, name='y')
        # 航班约束：每次航班最多仅能被选入解一次
        for j in range(self._flight_node_num):
            self._solver.add_constraint(self._solver.sum(route[i][j] * self._x_list[i]
                                                         for i in range(self._route_num)) + self._y_list[j] == 1,
                                        ctname=f'flight_node{j}')
        start = 0
        cid = 0
        # 飞机约束：每架飞机有一条路径
        for n in var_num_list:
            self._solver.add_constraint(self._solver.sum(self._x_list[i] for i in range(start, start + n)) <= 1,
                                        ctname=f'aircraft{cid}')
            start += n
            cid += 1

        self._solver.minimize(self._solver.sum(cost[i] * self._x_list[i] for i in range(self._route_num)) +
                              self._solver.sum(cancel[j] * self._y_list[j] for j in range(self._flight_node_num)))

    def print_info(self):
        for j in range(self._flight_node_num):
            print(self._solver.get_constraint_by_name('flight_node%s' % j))
        for cid in range(self._aircraft_num):
            print(self._solver.get_constraint_by_name('aircraft%s' % cid))
        # 输出目标函数
        print("Objective:")
        print(self._solver.get_objective_expr())
        self._solver.print_information()  # 输出模型信息

    def solve(self):
        self.result = self._solver.solve()
        if not self.result:
            self.result = self._solver.solve(log_output=True)  # 用来检查是否存在不可行约束
            print("当前问题无解")
            return None

    @property
    def solution_x(self) -> list:
        return [self.result.get_value('x_' + s) for s in self._var_name_list_x]

    @property
    def solution_y(self) -> list:
        return [self.result.get_value('y_' + s) for s in self._var_name_list_y]

    @property
    def flight_node_dual(self) -> list:
        return self._solver.dual_values(self._solver.find_matching_linear_constraints('flight_node'))

    @property
    def aircraft_dual(self) -> list:
        return self._solver.dual_values(self._solver.find_matching_linear_constraints('aircraft'))

    @property
    def optimal(self) -> float:
        return self._solver.objective_value


class ShortestPath(object):
    def __init__(self, ass_matrix: list[list], node_attr: list, edge_cost: list, relaxation=True):
        self.node_num = len(node_attr)  # number of node
        self.edge_num = len(edge_cost)  # number of edge
        self._var_name_list = [f'e{j}' for j in range(self.edge_num)]
        self.sp = Model(name="shortest path problem")
        if relaxation:
            self.var_list = self.sp.continuous_var_list(self._var_name_list, name='x')
        else:
            self.var_list = self.sp.binary_var_list(self._var_name_list, name='x')
        for i in range(self.node_num):
            row = ass_matrix[i]
            self.sp.add_constraint(self.sp.sum(row[j] * self.var_list[j] for j in range(self.edge_num)) == node_attr[i],
                                   ctname=f'node{i}')
        self.sp.min(self.sp.sum(edge_cost[j] * self.var_list[j] for j in range(self.node_num)))
        self.result = None

    def add_mutex_constraint(self, advance_flight_node_nums: list, graph_node_index: dict):
        k = 0
        for af_node_num in advance_flight_node_nums:
            if af_node_num in graph_node_index.keys():
                node_ct = [0] * self.edge_num
                indexs = graph_node_index[af_node_num]
                for i in indexs:
                    node_ct[i] = 1
                self.sp.add_constraint(self.sp.sum(node_ct[j] * self.var_list[j] for j in range(self.edge_num)) <= 1,
                                       ctname=f'cnode{k}')
                k += 1

    def print_info(self):
        # for j in range(self.node_num):
        #     print(self.sp.get_constraint_by_name('node%s' % j))
        #
        # # 输出目标函数
        # print("Objective:")
        # print(self.sp.get_objective_expr())
        self.sp.print_information()  # 输出模型信息

    def solve(self):
        self.result = self.sp.solve()
        if not self.result:
            self.result = self.sp.solve(log_output=True)  # 用来检查是否存在不可行约束
            print("当前问题无解")
            return None

    @property
    def solution(self) -> list:
        return [self.result.get_value('x_' + s) for s in self._var_name_list]

    @property
    def optimal(self) -> float:
        return self.sp.objective_value

    def is_int(self) -> bool:
        for i in self.solution:
            if i != int(i):
                return False
        return True


if __name__ == '__main__':
    var_num_lt = [3, 3, 2, 1, 4]  # 5架飞机，每架飞机拥有的路径数  ##某几架飞机的数值上升
    cost = [-8, -9, -10, -8, -7, -6, -7, -6, -5, -7, -4, -6, -8]  # 增加几项
    cancel = [1.2, 1.3, 1.1, 1.2, 1, 1.3, 1.4, 1.2, 1.1, 1, 1, 1.1, 1.3, 1.2, 1.1]  # 不变
    route = [[1, 0, 0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0],  # 0.0
             [0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],  # 0.1
             [0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0],  # 0.2
             [0, 0, 1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0],  # 1.0
             [0, 1, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],  # 1.1
             [0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0],  # 1.2
             [1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0],  # 2.0
             [0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1],  # 2.1
             [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0],  # 3.0
             [1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],  # 4.0
             [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 0, 0],  # 4.1
             [0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 1],  # 4.2
             [0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 0, 0]]  # 4.3
    cplex_solver = CplexSolver(route, cost, var_num_lt, cancel)
    cplex_solver.print_info()
    cplex_solver.solve()
