from kensu.pandas import DataFrame,Series
from kensu.utils.kensu_provider import KensuProvider
from gluonts.dataset.common import  ListDataset
from kensu.utils.helpers import eventually_report_in_mem
from kensu.numpy import ndarray
from kensu.client.models import Model,ModelPK,ModelRef,ModelTraining,ModelTrainingPK,ModelTrainingRef


import gluonts.mx.model.predictor as pred
class RepresentableBlockPredictor(pred.RepresentableBlockPredictor):

        def predict(self, Y, *args, **kwargs):
                if isinstance(Y, ListDataset):
                        new_Field = []
                        dep_fields = []
                        for element in Y.list_data:
                                new_dict = {}
                                for key in element.keys():
                                        item = element[key]
                                        if isinstance(item, DataFrame):
                                                new_item = item.get_df()
                                                dep_fields.append(new_item)
                                        elif isinstance(item, Series):
                                                new_item = item.get_s()
                                                dep_fields.append(new_item)
                                        elif isinstance(item, ndarray):
                                                new_item = item.get_nd()
                                                dep_fields.append(new_item)
                                        else:
                                                new_item = item
                                        new_dict[key] = new_item
                                new_Field.append(new_dict)
                        Y.list_data = new_Field

                result = super(RepresentableBlockPredictor, self).predict(dataset = Y, *args, **kwargs)
                return result

