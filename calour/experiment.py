'''
experiment (:mod:`calour.experiment`)
=====================================

.. currentmodule:: calour.experiment

Classes
^^^^^^^
.. autosummary::
   :toctree: generated

   Experiment

Functions
^^^^^^^^^
.. autosummary::
   :toctree: generated

   add_functions
'''

# ----------------------------------------------------------------------------
# Copyright (c) 2016--,  Calour development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
# ----------------------------------------------------------------------------

from logging import getLogger
from copy import deepcopy
from importlib import import_module
from functools import wraps
import inspect

import pandas as pd
import numpy as np
import scipy.sparse


logger = getLogger(__name__)


class Experiment:
    '''This class contains the data for a experiment or a meta experiment.

    The data set includes a data table (otu table, gene table,
    metabolomic table, or all those tables combined), a sample
    metadata table, and a feature metadata.

    Parameters
    ----------
    data : :class:`numpy.ndarray` or :class:`scipy.sparse.csr_matrix`
        The abundance table for OTUs, metabolites, genes, etc. Samples
        are in row and features in column
    sample_metadata : :class:`pandas.DataFrame`
        The metadata on the samples
    feature_metadata : :class:`pandas.DataFrame`
        The metadata on the features
    description : str
        name of experiment
    sparse : :class:`bool`
        store the data array in :class:`scipy.sparse.csr_matrix`
        or :class:`numpy.ndarray`

    Attributes
    ----------
    data : :class:`numpy.ndarray` or :class:`scipy.sparse.csr_matrix`
        The abundance table for OTUs, metabolites, genes, etc. Samples
        are in row and features in column
    sample_metadata : :class:`pandas.DataFrame`
        The metadata on the samples
    feature_metadata : :class:`pandas.DataFrame`
        The metadata on the features
    exp_metadata : dict
        metadata about the experiment (data md5, filenames, etc.)
    shape : tuple of (int, int)
        the dimension of data
    sparse : bool
        store the data as sparse matrix (scipy.sparse.csr_matrix) or numpy array.
    description : str
        name of the experiment

    See Also
    --------
    AmpliconExperiment
    '''
    def __init__(self, data, sample_metadata, feature_metadata=None,
                 exp_metadata={}, description='', sparse=True):
        self.data = data
        self.sample_metadata = sample_metadata
        self.feature_metadata = feature_metadata
        self.exp_metadata = exp_metadata
        self.description = description

        # the function calling history list
        self._call_history = []
        # whether to log to history
        self._log = True

        # flag if data array is sparse (True) or dense (False)
        self.sparse = sparse

        # remeber how many reads per sample/feature before any procesing
        self.sample_metadata['_calour_original_abundance'] = self.data.sum(axis=1)
        # self.feature_metadata['_calour_original_abundance'] = self.data.sum(axis=0)

    @property
    def sparse(self):
        return scipy.sparse.issparse(self.data)

    @sparse.setter
    def sparse(self, sparse):
        if sparse is True and not scipy.sparse.issparse(self.data):
            self.data = scipy.sparse.csr_matrix(self.data)
        elif sparse is False and scipy.sparse.issparse(self.data):
            self.data = self.data.toarray()

    def __repr__(self):
        '''Return a string representation of this object.'''
        return 'Experiment %s with %d samples, %d features' % (
            self.description, self.data.shape[0], self.data.shape[1])

    def __eq__(self, other):
        '''Check equality.

        It compares ``data``, ``sample_metadata``, and
        ``feature_metadata`` attributes.  to check sparsity and do
        the conversion if needed first.
        '''
        if self.sparse is True:
            data = self.data.toarray()
        else:
            data = self.data
        if other.sparse is True:
            other_data = other.data.toarray()
        else:
            other_data = other.data
        return (np.array_equal(data, other_data) and
                pd.DataFrame.equals(self.feature_metadata, other.feature_metadata) and
                pd.DataFrame.equals(self.sample_metadata, other.sample_metadata))

    def __ne__(self, other):
        return not (self == other)

    def copy(self):
        '''Copy the object.

        Returns
        -------
        Experiment
        '''
        return deepcopy(self)

    @staticmethod
    def _record_sig(func):
        '''Record the function calls to history.

        Note this require the function decorated to return an
        ``Experiment`` object.
        '''
        fn = func.__qualname__

        @wraps(func)
        def inner(*args, **kwargs):
            # this extra code here is to prevent recording func call
            # if the method is called inside another method.
            exp = args[0]
            log = exp._log
            try:
                new_exp = func(*args, **kwargs)
                if exp._log is True:
                    param = ['%r' % i for i in args[1:]] + ['%s=%r' % (k, v) for k, v in kwargs.items()]
                    param = ', '.join(param)
                    new_exp._call_history.append('{0}({1})'.format(fn, param))
                    exp._log = False
            finally:
                # set log status back
                exp._log = log
            return new_exp

        return inner

    def get_data(self, sparse=None, copy=False):
        '''Get the data as a 2d array

        Get the data 2d array (each column is a feature and row is a sample)

        Parameters
        ----------
        sparse : None or bool (optional)
            None (default) to pass original data (sparse or dense).
            True to get as sparse. False to get as dense
        copy : bool (optional)
            True to get a copy of the data; otherwise, it can be
            the original data or a copy (default).

        Returns
        -------
        ``Experiment.data``
        '''
        if sparse is None:
            if copy:
                return self.data.copy()
            else:
                return self.data
        elif sparse:
            if self.sparse:
                if copy:
                    return self.data.copy()
                else:
                    return self.data
            else:
                return scipy.sparse.csr_matrix(self.data)
        else:
            if self.sparse:
                return self.data.toarray()
            else:
                if copy:
                    return self.data.copy()
                else:
                    return self.data

    @property
    def shape(self):
        return self.get_data().shape

    def reorder(self, new_order, axis=0, inplace=False):
        '''Reorder according to indices in the new order.

        Note that we can also drop samples in new order.

        Parameters
        ----------
        new_order : Iterable of int or boolean mask
            the order of new indices
        axis : 0 for samples or 1 for features
            the axis where the reorder occurs
        inplace : bool, optional
            reorder in place.

        Returns
        -------
        Experiment
            experiment with reordered samples
        '''
        if inplace is False:
            exp = deepcopy(self)
        else:
            exp = self
        # make it a np array; otherwise the slicing won't work if the new_order is
        # a list of boolean and data is sparse matrix. For example:
        # from scipy.sparse import csr_matrix
        # a = csr_matrix((3, 4), dtype=np.int8)
        # In [125]: a[[False, False, False], :]
        # Out[125]:
        # <3x4 sparse matrix of type '<class 'numpy.int8'>'

        # In [126]: a[np.array([False, False, False]), :]
        # Out[126]:
        # <0x4 sparse matrix of type '<class 'numpy.int8'>'
        new_order = np.array(new_order)
        if axis == 0:
            exp.data = exp.data[new_order, :]
            exp.sample_metadata = exp.sample_metadata.iloc[new_order, :]
        else:
            exp.data = exp.data[:, new_order]
            exp.feature_metadata = exp.feature_metadata.iloc[new_order, :]
        return exp

    def to_pandas(self, sample_field=None, feature_field=None, sparse=None):
        '''Get a pandas dataframe of the abundances
        Samples are rows, features are columns. Can specify the metadata fields
        for the index (default is sample_metadata index) and column labels
        (default is feature_metadata index)

        Parameters
        ----------
        sample_field : str or None (optional)
            Name of the sample_metadata column to use for index.
            None (default) is the sample_metadata index
        feature_field : str or None (optional)
            Name of the feature_metadata column to use for column names.
            None (default) is the feature_metadata index
        sparse: bool or None (optional)
            None (default) to get sparsity based on the underlying Experiment sparsity
            True to force to sparse pandas.Dataframe
            False to force to standard pandas.Dataframe

        Returns
        -------
        ``pandas.Dataframe`` or ``pandas.SparseDataframe``
        '''
        if sample_field is None:
            ind = self.sample_metadata.index
        else:
            ind = self.sample_metadata[sample_field]
        if feature_field is None:
            cols = self.feature_metadata.index
        else:
            cols = self.feature_metadata[feature_field]

        if sparse is not None:
            self.sparse = sparse

        if self.sparse:
            # create list of sparse rows
            sr = [pd.SparseSeries(self.data[i, :].toarray().ravel(), fill_value=0) for i in np.arange(self.data.shape[0])]
            df = pd.SparseDataFrame(sr, index=ind, columns=cols)
        else:
            df = pd.DataFrame(self.data, index=ind, columns=cols, copy=True)
        return df

    @classmethod
    def from_pandas(cls, df, exp=None):
        '''Convert a Pandas DataFrame into an experiment.

        Can use an existing calour Experimebt (exp) (if supplied) to
        obtain feature and sample metadata.  Note currently only works
        with non-sparse DataFrame

        Parameters
        ----------
        df : Pandas.DataFrame
            The dataframe to use. should contain samples in rows, features in columns.
            Index values will be used for the sample_metadata index and column names will be used for feature_metadata index
        exp : Experiment (optional)
            If not None, use sample and feature metadata from the experiment

        Returns
        -------
        Experiment
            with non-sparse data

        '''
        if exp is None:
            sample_metadata = pd.DataFrame(index=df.index)
            sample_metadata['id'] = sample_metadata.index
            feature_metadata = pd.DataFrame(index=df.columns)
            feature_metadata['id'] = feature_metadata.index
            exp_metadata = {}
            description = 'From Pandas DataFrame'
        else:
            description = exp.description + ' From Pandas'
            exp_metadata = exp.exp_metadata
            sample_metadata = exp.sample_metadata.loc[df.index.values, ]
            feature_metadata = exp.feature_metadata.loc[df.columns.values, ]
            cls = exp.__class__

        # print(sample_metadata)
        newexp = cls(df.values, sample_metadata, feature_metadata,
                     exp_metadata=exp_metadata, description=description, sparse=False)
        return newexp


def add_functions(cls,
                  modules=['.io', '.sorting', '.filtering', '.analysis',
                           '.transforming', '.heatmap.heatmap', '.plotting',
                           '.manipulation', '.analysis']):
    '''Dynamically add functions to the class as methods.

    Parameters
    ----------
    cls : ``class`` object
        The class that the functions will be added to
    modules : iterable of str
        The modules where the functions are defined
    '''
    for module_name in modules:
        module = import_module(module_name, 'calour')
        functions = inspect.getmembers(module, inspect.isfunction)
        for fn, f in functions:
            # skip private functions
            if not fn.startswith('_'):
                setattr(cls, fn, f)
