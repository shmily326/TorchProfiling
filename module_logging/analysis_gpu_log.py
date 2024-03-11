# from inspect import ArgSpec
# import sys
import os.path as osp
# import pandas as pd
import re
import prettytable as pt
# import pathlib


# import pandas.DataFrame as df
def parse_one_log(log_file_path):
    if not osp.exists(log_file_path):
        print("Log file {} does not exist".format(log_file_path))
        raise FileNotFoundError("log file {} doesn't find".format(log_file_path))
    lines = []
    with open(log_file_path, "r") as f:
        lines = f.readlines()

    table_data = []

    collecting = False
    iteration_begin = False
    # xdnn_pytorch_op_list = []
    # xdnn_pytorch_op_times = []
    total_kernel_consumed = 0
    # xdnn_pytorch_op_dict = {}
    op_name = ""
    xdnn_pytorch_op_name = ""
    # collect the total time in the net
    total_time_dict = {}
    total_iteration_time = 0
    module_list = []
    module_total_kernel_consumed = 0
    for line in lines:
        if not iteration_begin:
            if "iteration" in line and "learning" in line and "loss" in line:
                iteration_begin = True
                print(">>>>>>>>>>>>start a collection iteration")
                print(line)
            continue

        # finish the collection of one iteration
        if iteration_begin:
            if "iteration" in line and "learning" in line and "loss" in line:
                print(line)
                print(">>>>>>>>>>>>end a collection iteration")
                break
        # print(line)

        if line.startswith("[BEGIN FORWARD]:") or line.startswith("[BEGINE BACKWARD]"):
            if len(module_list) > 0 and module_total_kernel_consumed > 0:
                data = {
                    "Module": "",
                    "Name":  "",
                    "TOTAL TIME": "",
                    "MODULE TOTAL TIME": module_total_kernel_consumed,
                }
                table_data.append(data)

            module_list.append(line.rstrip("\n").split(":")[-1])
            module_total_kernel_consumed = 0

        if line.startswith("[END FORWARD]:") or line.startswith("[END BACKWARD]"):
            data = {
                "Module": "",
                "Name":  "",
                "TOTAL TIME": "",
                "MODULE TOTAL TIME": module_total_kernel_consumed,
            }
            table_data.append(data)
            module_total_kernel_consumed = 0

            module_name = line.rstrip("\n").split(":")[-1]
            if module_name == module_list[-1]:
                module_list.pop()
            else:
                raise Exception("not find the module name in module list")

        if not collecting:
            if line.startswith("[START_SYMBOL]:"):
                collecting = True
                op_name = line.rstrip("\n").split(":")[-1]
            continue

        if line.startswith("[END_SYMBOL]:"):
            end_name = line.rstrip("\n").split(":")[-1]
            # if end_name != op_name:
            if not op_name in end_name:
                raise Exception(
                    "end symbol name {} is not equal to start symbol name {}".format(
                        end_name, op_name
                    )
                )

            module_name = ""
            if len(module_list) > 0:
                module_name = module_list[-1]

            data = {
                "Module": module_name,
                "Name": op_name,
                "TOTAL TIME": total_kernel_consumed,
                "MODULE TOTAL TIME": "",
            }
            table_data.append(data)

            if op_name in total_time_dict:
                total_time_dict[op_name] += total_kernel_consumed
            else:
                total_time_dict[op_name] = total_kernel_consumed

            op_name = ""
            total_kernel_consumed = 0
            collecting = False
            continue

        #if line.startswith("[CUDA_PROF]"):
        if line.startswith("DURATION:"):
            strs = line.split(" ")

            time = float(strs[-1])
            total_kernel_consumed += time
            total_iteration_time += time
            module_total_kernel_consumed += total_kernel_consumed

    print("==================================")
    # sort table_date
    def take_total_time(data):
        """get the total time of each op"""
        return data["TOTAL TIME"]
    
    print("table size: {}".format(len(table_data)))

    table = pt.PrettyTable(
        ["Module", "Name", "TOTAL TIME", "MODULE TOTAL TIME"]
    )
    for data in table_data:
        table.add_row(
            [
                data["Module"],
                data["Name"],
                data["TOTAL TIME"],
                data["MODULE TOTAL TIME"],
            ]
        )
    
    print("construct table 2: ")

    # summarize_table_data = []
    # total_time_dict = sorted(total_time_dict.items(), key=lambda x: x[1], reverse=True)

    # if total_iteration_time == 0:
    #     return

    table2 = pt.PrettyTable(["Name", "TOTAL TIME", "PERCENT"])
    # for elem in total_time_dict:
    #     table2.add_row([elem[0], elem[1], elem[1] / total_iteration_time])

    print("construct table 3: ")
    table3 = pt.PrettyTable(["TOTAL TIME"])
    table3.add_row([total_iteration_time])

    return table, table2, table3


def parse_log(log_path):
    """
    Args:
        log_file_path: the path of log file
        gen_csv: the path of csv file to save

    return:
        None
    """

    print("log_path: {}".format(log_path))
    table, table1, table2 = parse_one_log(log_path)
    print("print table: ")
    print(table)
    # print(table1)
    print(table2)
