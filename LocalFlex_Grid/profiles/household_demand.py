import numpy as np
N = 96
t = np.arange(N) / 4.0
solar_shape = np.clip(np.sin(np.pi * (t - 6.5) / 11.5), 0, None)
home_shape = (0.30 + 0.5*np.exp(-((t-7.5)/1.2)**2) + 0.25*np.exp(-((t-13)/2.5)**2)
              + 1.3*np.exp(-((t-20)/1.8)**2))                 # kW per home (before size factor)
