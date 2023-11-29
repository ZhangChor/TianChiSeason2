from scipy.sparse import csr_matrix, csc_matrix, lil_matrix, coo_matrix, hstack, vstack
from time import time as current_time


def matrix_col_insert(matrix, index: int, cols_data):
    return hstack([matrix[:, :index], cols_data, matrix[:, index:]])


def matrix_row_insert(matrix, index: int, rows_data):
    return vstack([matrix[:index, :], rows_data, matrix[index:, :]]).tolil()


if __name__ == '__main__':
    # row = [0, 1, 0, 2, 0, 3, 1, 3, 2, 4, 3, 4, 0, 1]
    # col = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6]
    # val = [1, -1] * 7
    # # c = csc_matrix((val, (row, col)), shape=(5, 7))  # 按列压缩
    # # r = csr_matrix((val, (row, col)), shape=(5, 7))  # 按行压缩
    # o = coo_matrix((val, (row, col)), shape=(5, 7))
    # lil: lil_matrix = o.tolil()
    lil = lil_matrix([0] * 5)
    # n_row = [2, 3]
    # n_val = [1, -1]
    # new_column = csr_matrix((n_val, (n_row, [0, 0])), shape=(5, 1))
    # new_column_data = [0, 0, 1, -1, 0]
    # insert_after_column = 0
    # result = matrix_col_insert(lil, 2, new_column)
    lil[0, 1] = 1
    lil[0, 4] = 1
    add_mat = lil_matrix([0] * 5)
    add_mat[0, 0] = 1
    add_mat[0, 2] = 1
    lil = matrix_row_insert(lil, 0, add_mat)
    print(lil.toarray())
    lil_col = lil.tocsc()
    row, col = lil_col[:, 1].nonzero()
    print("col", col)
    print("row", row)

