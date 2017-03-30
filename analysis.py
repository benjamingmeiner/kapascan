import numpy as np
from skimage import draw

def wiener(y, h, n, s=1):
    """
    2D Wiener deconvolution. Implemented as defined in
    https://en.wikipedia.org/wiki/Wiener_deconvolution
 
    Parameters
    ----------
    y : 2D array
        The observed signal
 
    h : 2D array
        The impulse response (point spread function) of the system
 
    n : scalar or 2D array
        The signal from which the power spectral density of the noise is
        calculated. If n is a scalar the value is used directly as the PSD.
 
    s : scalar or 2D array, optional
        The signal from which the power spectral density of the origininal
        signal is calculated. If s is a scalar the value is used directly as
        the PSD.
 
    Returns
    -------
    x : 2D array
        An estimate of the original signal.
    """
 
    # pad signal with zeros to full length of actual convolution
    widths = [[width // 2] for width in h.shape]
    y_padded = np.pad(y, widths, mode='constant', constant_values=0)
    # minimal length for fft to prevent circular convolution
    length = [sy + sh - 1  for sy, sh in zip(y_padded.shape, h.shape)]

    if not np.isscalar(n):
        N = np.absolute(np.fft.rfft2(n, length))**2
    if not np.isscalar(s):
        S = np.absolute(np.fft.rfft2(s, length))**2
 
    Y = np.fft.rfft2(y_padded, length)
    H = np.fft.rfft2(h, length)
    G = (np.conj(H) * S) / (np.absolute(H)**2 * S + N)
    X = G * Y
    x = np.fft.irfft2(X, length)
 
    return x[:y.shape[0],:y.shape[1]].copy()


def sensor_function(diameter):
    """
    Generates a devonvolution kernel with a circular shape.

    Parameters
    ----------
    diameter : int
        diameter of the circle

    Returns
    -------
    sf : 2D array
        The deconvolution kernel
    """
    radius = diameter // 2
    sf = np.zeros((diameter, diameter))
    r, c, val = draw.circle_perimeter_aa(radius, radius, radius)
    sf[r, c] = val
    r, c, = draw.circle(radius, radius, radius)
    sf[r, c] = 1
    sf /= sf.sum()
    return sf 
 
