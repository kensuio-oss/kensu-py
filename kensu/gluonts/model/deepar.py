from kensu.pandas import DataFrame,Series
from kensu.utils.kensu_provider import KensuProvider
import gluonts.model.deepar as dp
from gluonts.dataset.common import  ListDataset
from kensu.utils.helpers import eventually_report_in_mem
from kensu.numpy import ndarray
from kensu.client.models import Model,ModelPK,ModelRef,ModelTraining,ModelTrainingPK,ModelTrainingRef
from kensu.gluonts.mx.model.predictor import RepresentableBlockPredictor

class DeepAREstimator(dp.DeepAREstimator):

    def train(self, X):
        if isinstance(X,ListDataset):
            new_Field = []
            old_Field = X.list_data
            dep_fields = []
            for element in X.list_data:
                new_dict = {}
                for key in element.keys():
                    item = element[key]
                    if isinstance(item,DataFrame):
                        new_item = item.get_df()
                        dep_fields.append(new_item)
                    elif isinstance(item,Series):
                        new_item = item.get_s()
                        dep_fields.append(new_item)
                    elif isinstance(item,ndarray):
                        new_item = item.get_nd()
                        dep_fields.append(new_item)
                    else:
                        new_item = item
                    new_dict[key] = new_item
                new_Field.append(new_dict)
            X.list_data = new_Field

        result = super(DeepAREstimator,self).train(X)
        result.__class__ = RepresentableBlockPredictor
        if isinstance(X,ListDataset):
            X.list_data = old_Field
        return result


