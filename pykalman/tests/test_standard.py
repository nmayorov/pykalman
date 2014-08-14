import pickle
from io import BytesIO
from unittest import TestCase

import numpy as np
from numpy.testing import assert_array_almost_equal
from scipy import linalg
from nose.tools import assert_true

from pykalman import KalmanFilter
from pykalman.datasets import load_robot


class KalmanFilterTests(object):
    """All of the actual tests to check against an implementation of the usual
    Kalman Filter. Abstract so that sister implementations can re-use these
    tests.
    """

    def test_kalman_sampling(self):
        kf = self.KF(
            self.data.transition_matrix,
            self.data.observation_matrix,
            self.data.transition_covariance,
            self.data.observation_covariance,
            self.data.transition_offsets,
            self.data.observation_offset,
            self.data.initial_state_mean,
            self.data.initial_state_covariance)

        (x, z) = kf.sample(100)
        assert_true(x.shape == (100, self.data.transition_matrix.shape[0]))
        assert_true(z.shape == (100, self.data.observation_matrix.shape[0]))

    def test_kalman_filter_update(self):
        kf = self.KF(
            self.data.transition_matrix,
            self.data.observation_matrix,
            self.data.transition_covariance,
            self.data.observation_covariance,
            self.data.transition_offsets,
            self.data.observation_offset,
            self.data.initial_state_mean,
            self.data.initial_state_covariance)

        # use Kalman Filter
        (x_filt, V_filt) = kf.filter(X=self.data.observations)

        # use online Kalman Filter
        n_timesteps = self.data.observations.shape[0]
        n_dim_obs, n_dim_state = self.data.observation_matrix.shape
        kf2 = self.KF(n_dim_state=n_dim_state, n_dim_obs=n_dim_obs)
        x_filt2 = np.zeros((n_timesteps, n_dim_state))
        V_filt2 = np.zeros((n_timesteps, n_dim_state, n_dim_state))
        for t in range(n_timesteps - 1):
            if t == 0:
                x_filt2[0] = self.data.initial_state_mean
                V_filt2[0] = self.data.initial_state_covariance
            (x_filt2[t + 1], V_filt2[t + 1]) = kf2.filter_update(
                x_filt2[t], V_filt2[t],
                observation=self.data.observations[t + 1],
                transition_matrix=self.data.transition_matrix,
                transition_offset=self.data.transition_offsets[t],
                transition_covariance=self.data.transition_covariance,
                observation_matrix=self.data.observation_matrix,
                observation_offset=self.data.observation_offset,
                observation_covariance=self.data.observation_covariance
            )
        assert_array_almost_equal(x_filt, x_filt2)
        assert_array_almost_equal(V_filt, V_filt2)

    def test_kalman_filter(self):
        kf = self.KF(
            self.data.transition_matrix,
            self.data.observation_matrix,
            self.data.transition_covariance,
            self.data.observation_covariance,
            self.data.transition_offsets,
            self.data.observation_offset,
            self.data.initial_state_mean,
            self.data.initial_state_covariance)

        (x_filt, V_filt) = kf.filter(X=self.data.observations)
        assert_array_almost_equal(
            x_filt[:500],
            self.data.filtered_state_means[:500],
            decimal=7
        )
        assert_array_almost_equal(
            V_filt[:500],
            self.data.filtered_state_covariances[:500],
            decimal=7
        )

    def test_kalman_predict(self):
        kf = self.KF(
            self.data.transition_matrix,
            self.data.observation_matrix,
            self.data.transition_covariance,
            self.data.observation_covariance,
            self.data.transition_offsets,
            self.data.observation_offset,
            self.data.initial_state_mean,
            self.data.initial_state_covariance)

        x_smooth = kf.smooth(X=self.data.observations)[0]
        assert_array_almost_equal(
            x_smooth[:501],
            self.data.smoothed_state_means[:501],
            decimal=7
        )

    def test_kalman_fit(self):
        # check against MATLAB datase
        kf = self.KF(
            self.data.transition_matrix,
            self.data.observation_matrix,
            self.data.initial_transition_covariance,
            self.data.initial_observation_covariance,
            self.data.transition_offsets,
            self.data.observation_offset,
            self.data.initial_state_mean,
            self.data.initial_state_covariance,
            em_vars=['transition_covariances', 'observation_covariances'])

        loglikelihoods = np.zeros(5)
        for i in range(len(loglikelihoods)):
            loglikelihoods[i] = kf.loglikelihood(self.data.observations)
            kf.em(X=self.data.observations, n_iter=1)

        print(loglikelihoods, self.data.loglikelihoods[:5], sep='\n')

        assert_true(np.allclose(loglikelihoods, self.data.loglikelihoods[:5]))

        # check that EM for all parameters is working
        kf.em_vars = 'all'
        n_timesteps = 30
        for i in range(len(loglikelihoods)):
            kf.em(X=self.data.observations[0:n_timesteps], n_iter=1)
            loglikelihoods[i] = kf.loglikelihood(self.data.observations[0:n_timesteps])
        for i in range(len(loglikelihoods) - 1):
            assert_true(loglikelihoods[i] < loglikelihoods[i + 1])

    def test_kalman_initialize_parameters(self):
        self.check_dims(5, 1, {'transition_matrices': np.eye(5)})
        self.check_dims(1, 3, {'observation_offsets': np.zeros(3)})
        self.check_dims(2, 3, {'transition_covariances': np.eye(2),
                          'observation_offsets': np.zeros(3)})
        self.check_dims(3, 2, {'n_dim_state': 3, 'n_dim_obs': 2})
        self.check_dims(4, 1, {'initial_state_mean': np.zeros(4)})

    def check_dims(self, n_dim_state, n_dim_obs, kwargs):
        kf = self.KF(**kwargs)
        (transition_matrices, transition_offsets, transition_covariance,
         observation_matrices, observation_offsets, observation_covariance,
         initial_state_mean, initial_state_covariance) = (
            kf._initialize_parameters()
        )
        assert_true(transition_matrices.shape == (n_dim_state, n_dim_state))
        assert_true(transition_offsets.shape == (n_dim_state,))
        assert_true(transition_covariance.shape == (n_dim_state, n_dim_state))
        assert_true(observation_matrices.shape == (n_dim_obs, n_dim_state))
        assert_true(observation_offsets.shape == (n_dim_obs,))
        assert_true(observation_covariance.shape == (n_dim_obs, n_dim_obs))
        assert_true(initial_state_mean.shape == (n_dim_state,))
        assert_true(
            initial_state_covariance.shape == (n_dim_state, n_dim_state)
        )

    def test_kalman_pickle(self):
        kf = self.KF(
            self.data.transition_matrix,
            self.data.observation_matrix,
            self.data.transition_covariance,
            self.data.observation_covariance,
            self.data.transition_offsets,
            self.data.observation_offset,
            self.data.initial_state_mean,
            self.data.initial_state_covariance,
            em_vars='all')

        # train and get log likelihood
        X = self.data.observations[0:10]
        kf = kf.em(X, n_iter=5)
        loglikelihood = kf.loglikelihood(X)

        # pickle Kalman Filter
        store = BytesIO()
        pickle.dump(kf, store)
        clf = pickle.load(BytesIO(store.getvalue()))

        # check that parameters came out already
        np.testing.assert_almost_equal(loglikelihood, kf.loglikelihood(X))


class KalmanFilterTestSuite(TestCase, KalmanFilterTests):
    """Class that nose can pick up on to actually run Kalman Filter tests
    against default implementation.
    """

    def setUp(self):
        self.KF = KalmanFilter
        self.data = load_robot()