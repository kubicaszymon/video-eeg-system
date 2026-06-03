from scipy.optimize import curve_fit
from scipy.signal import iirpeak, freqz, iirnotch
import numpy as np
import sys
import pylab as pb

"""
USES CSV FFT SAVED FROM SVAROG TO ALIGN/CHECK FILTERS FOR IMPEDANCE
THIS IS A SCRIPT TO RUN MANUALLY TO CHECK IMPEDANCE FILTERS MATCH TO ACTUAL SIGNAL OF THE IMPEDANCE CURRENT
TO DECIDE ON IMPEDANCE FILTER BANDWITH
"""

def fit_iirpeak(f, fft_data):
    freqs = fft_data[:, 0]
    powers = fft_data[:, 1]
    bw = 20
    mask = (freqs > (f / 4 - bw / 2) )* (freqs < (f / 4 + bw / 2))
    freqs = freqs[mask]
    powers = powers[mask]

    def curve(x, Q, scale, offset):
        b, a = iirpeak((f / 4) / (f / 2), Q)
        worN = freqs / (f / 2) * np.pi
        w, h = freqz(b, a, worN=worN)
        w = w * f * 2 / np.pi
        t = np.abs(h) ** 2
        return t * scale + offset

    fit = curve_fit(curve, freqs, powers, p0=[8000, 1, 0], method='lm', ftol=1e-12, gtol=1e-12)
    Q, scale, offset = fit[0]
    print("Q {} scale {} offset {}, f {}".format(Q, scale, offset, f))
    return Q, scale, offset

def visualise(fft_data, f, Q, scale, offset):
    pb.figure()
    freqs = fft_data[:, 0]
    powers = fft_data[:, 1]
    bw = 60
    mask = (freqs > (f / 4 - bw / 2) )* (freqs < (f / 4 + bw / 2))
    freqs = freqs[mask]
    powers = powers[mask]

    # b, a = iirpeak((f / 4) / (f / 2), Q)
    # worN = freqs / (f / 2) * np.pi
    # w, h = freqz(b, a, worN=worN)
    # w = w * (f / 2) / np.pi
    # t = np.abs(h) ** 2 * scale + offset
    #
    pb.plot(freqs, powers, label='REAL')
    # pb.plot(w, t, label='filter')

    # b, a = iirpeak((f / 4) / (f / 2), 200)
    # worN = freqs / (f / 2) * np.pi
    # w, h = freqz(b, a, worN=worN)
    # w = w * (f / 2) / np.pi
    # t = np.abs(h) ** 2 * scale + offset
    # pb.plot(w, t, label='filter 200')
    pb.title(str(f))

    bw = 5
    Q = f / 4 / bw
    b, a = iirpeak((f / 4) / (f / 2), Q)
    worN = freqs / (f / 2) * np.pi
    w, h = freqz(b, a, worN=worN)
    w = w * (f / 2) / np.pi
    t = np.abs(h) ** 2 * scale + offset
    pb.plot(w, t, label='filter bw {} Q: {}'.format(bw, Q))
    print('custom Q at 5 BW: {}'.format(Q))


    # Q = f / 4 / 125 * 200 if f <= 2000 else f / 4 / 125 * 100
    # if f <= 500:
    #     Q = 800
    # elif f <= 2000:
    #     Q = 800
    # elif f <= 4000:
    #     Q = 800
    # elif f <= 8000:
    #     Q = 800
    # elif f <= 16000:
    #     Q = 800
    #
    # b, a = iirpeak((f / 4) / (f / 2), Q)
    # worN = freqs / (f / 2) * np.pi
    # w, h = freqz(b, a, worN=worN)
    # w = w * (f / 2) / np.pi
    # t = np.abs(h) ** 2 * scale + offset
    # pb.plot(w, t, label='filter Q: {}'.format(Q))
    # print('custom Q at 0.6 BW: {}'.format(Q))

    pb.legend()


def visualise2(f, fft_data):
    pb.figure()

    freqs = fft_data[:, 0]
    Q = f / 4 / 0.6
    b, a = iirnotch((f / 4) / (f / 2), Q=Q)
    worN = freqs / (f / 2) * np.pi
    w, h = freqz(b, a, worN=worN)
    w = w * (f / 2) / np.pi
    t = np.abs(h) ** 2 * scale + offset
    pb.plot(w, t, label='filter 200')
    pb.title(str(f))
    pb.legend()


if __name__ == '__main__':
    folder = sys.argv[1]
    freqs = [500, 1000, 2000, 4000, 8000, 16000]
    for f in freqs:
        fft_data = np.loadtxt(folder + '/{}.csv'.format(f), delimiter=';')
        Q, scale, offset = fit_iirpeak(f, fft_data)
        visualise(fft_data, f, Q, scale, offset)
        # visualise2(f, fft_data)
    pb.show()
