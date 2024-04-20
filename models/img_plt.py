import matplotlib.pyplot as plt
import pickle
from models.iterate import ColumnGeneration


def line_plt(cg: ColumnGeneration):
    y = cg.optimal_value_list
    x = range(len(y))
    ac = len(cg.aircraft_dual)
    plt.plot(x, y, 'b*-', alpha=0.5, label=f'AC{ac}', )
    plt.xlabel('Iterations')
    plt.ylabel('Objective Value')
    plt.legend()
    plt.show()


def save_variables(variable, file_name='variables.pkl'):
    with open(file_name, 'wb') as file:
        pickle.dump(variable, file)


def load_variables(file_name='variables.pkl'):
    try:
        with open(file_name, 'rb') as file:
            return pickle.load(file)
    except FileNotFoundError:
        return None
