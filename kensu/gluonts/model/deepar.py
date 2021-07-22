from kensu.gluonts.ksu_utils.dataset_helpers import make_dataset_reliable
import gluonts.model.deepar as dp
from gluonts.dataset.common import  ListDataset
from kensu.gluonts.mx.model.predictor import RepresentableBlockPredictor

class DeepAREstimator(dp.DeepAREstimator):

    def train(self, X):
        X, old_Field, dep_fields = make_dataset_reliable(X)
        if isinstance(X,ListDataset):
            print(X.list_data[0]['target'].__class__)

        result = super(DeepAREstimator,self).train(X)
        result.__class__ = RepresentableBlockPredictor
        if isinstance(X,ListDataset):
            X.list_data = old_Field
        return result

