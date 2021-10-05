import os
# disable Kensu collector when requested to do so (e.g. inside Apache Spark executor nodes)
if "KSU_DISABLE_PY_COLLECTOR" in os.environ:
    from sklearn import model_selection
    from sklearn.linear_model import LogisticRegression
else:
    from kensu.sklearn import model_selection
    from kensu.sklearn.linear_model import LogisticRegression
