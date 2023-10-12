def my_f_1():
    print("my_f_1 called")


def my_f_2():
    print("my_f_2 called")
    my_f_1()


my_f_2()
