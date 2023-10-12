import sys


def my_func(my_arg1="my_arg1_default_value"):
    if my_arg1 == "my_arg1_default_value":
        my_func(my_arg1=f"imported sys, called myself")

