import logging
import re
from typing import Dict, Iterator, NamedTuple, Optional, Tuple

# Third-party imports

import gluonts  # noqa
from gluonts import transform
from gluonts.core.serde import load_code
from gluonts.dataset.common import DataEntry, Dataset
from gluonts.dataset.stat import (
    DatasetStatistics,
    calculate_dataset_statistics,
)
from gluonts.evaluation import Evaluator
from gluonts.model.estimator import Estimator
from gluonts.model.forecast import Forecast
from gluonts.model.predictor import Predictor
from gluonts.support.util import maybe_len
from gluonts.transform import TransformedDataset
import pandas as pd
from kensu.gluonts.ksu_utils.dataset_helpers import make_dataset_reliable


def make_evaluation_predictions(
        dataset: Dataset, predictor: Predictor, num_samples: int
) -> Tuple[Iterator[Forecast], Iterator[pd.Series]]:
    import pandas as pd

    prediction_length = predictor.prediction_length
    freq = predictor.freq
    lead_time = predictor.lead_time

    def add_ts_dataframe(
            data_iterator: Iterator[DataEntry],
    ) -> Iterator[DataEntry]:
        for data_entry in data_iterator:
            data = data_entry.copy()
            index = pd.date_range(
                start=data["start"],
                freq=freq,
                periods=data["target"].shape[-1],
            )
            data["ts"] = pd.DataFrame(
                index=index, data=data["target"].transpose()
            )
            yield data

    def ts_iter(dataset: Dataset) -> pd.DataFrame:
        dataset, old, dep_fields = make_dataset_reliable(dataset)
        for data_entry in add_ts_dataframe(iter(dataset)):
            yield data_entry["ts"]
        dataset.list_data = old

    def truncate_target(data):
        data = data.copy()
        target = data["target"]
        assert (
                target.shape[-1] >= prediction_length
        )  # handles multivariate case (target_dim, history_length)
        data["target"] = target[..., : -prediction_length - lead_time]
        return data

    # TODO filter out time series with target shorter than prediction length
    # TODO or fix the evaluator so it supports missing values instead (all
    # TODO the test set may be gone otherwise with such a filtering)

    dataset_trunc = TransformedDataset(
        dataset, transformation=transform.AdhocTransform(truncate_target)
    )

    return (predictor.predict(dataset_trunc, num_samples=num_samples), ts_iter(dataset))