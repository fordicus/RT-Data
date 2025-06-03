% PREAMBLE
\usepackage{listings}
\usepackage{xcolor}
\renewcommand{\lstlistingname}{Code}
\renewcommand{\thelstlisting}{Code-\arabic{lstlisting}}  % Custom Code-X format

\lstset{
  basicstyle=\ttfamily\normalsize,
  breaklines=true,
  breakatwhitespace=true,
  linewidth=0.95\linewidth,
  frame=single,
  backgroundcolor=\color{gray!5},
  captionpos=b,
  keywordstyle=\color{blue},
  commentstyle=\color{gray!60},
  showstringspaces=false
}

% BODY
A simple Python example to do such an ADF test is given in Code~\ref{code:adf}.

\begin{minipage}{0.95\linewidth}
\begin{lstlisting}[
  language=Python,
  caption={ADF Test on Log Returns of Price Series\label{code:adf}}, % ✅ label goes here
  xleftmargin=0.7em,
  framexleftmargin=0.7em
]
import numpy as np
from statsmodels.tsa.stattools import adfuller

# Price time series (e.g., BTC price)
price = np.array([100, 102, 105, 110, 114, 113, 115, 118, 120, 122], dtype=float)

# Compute log returns
log_return = np.diff(np.log(price))

# Perform Augmented Dickey-Fuller test
result = adfuller(log_return)

# Print test results
print(f"ADF Statistic: {result[0]:.4f}")
print(f"p-value: {result[1]:.4f}")
print(f"Lags Used: {result[2]}")
print(f"# Observations: {result[3]}")
print("Critical Values:")
for key, value in result[4].items():
    print(f"   {key}: {value:.4f}")

# Interpretation of result
if result[1] < 0.05:
    print("stationary")
else:
    print("non-stationary")
\end{lstlisting}
\end{minipage}
