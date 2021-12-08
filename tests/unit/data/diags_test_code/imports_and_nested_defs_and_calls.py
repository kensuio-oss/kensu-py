import pandas


def my_f_1():
    print("my_f_1 called")
    df = pandas.DataFrame()


def my_f_2():
    print("my_f_2 called")
    my_f_1()
    df2 = pandas.DataFrame()
    def my_f_3():
        def my_f_4():
            pass
        my_f_4()
    my_f_3()


my_f_2()
