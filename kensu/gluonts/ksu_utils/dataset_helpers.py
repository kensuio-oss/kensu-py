from gluonts.dataset.common import ListDataset
# FIXME: currently if any of imported libs were missing (pandas,numpy) it'd fail!
#  => so we'd need to extract an additional abstraction
from kensu.pandas.data_frame import DataFrame,Series
from kensu.numpy import ndarray

def make_dataset_reliable(dataset):
    dep_fields = []
    old_Field = []
    if isinstance(dataset, ListDataset):
        new_Field = []
        old_Field = dataset.list_data
        for element in dataset.list_data:
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
                    dep_fields.append(item)
                else:
                    new_item = item
                new_dict[key] = new_item
            new_Field.append(new_dict)
        dataset.list_data = new_Field
        return (dataset, old_Field, dep_fields)
    return (dataset, old_Field, dep_fields)
