import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from reproduce_thresholds import endpoints_from_xlsx

class RawEndpointTests(unittest.TestCase):
    def test_finite_last_is_selected_within_each_causal_window(self):
        frame = pd.DataFrame({'index': [0,1,2,3], 'PosNED[3]': [-1,-2,-3,np.nan],
          'VelNED[1]': [1,2,3,np.nan], 'VelNED[2]': [0,0,0,0], 'VelNED[3]': [0,0,0,0],
          'Eular[1]': [.1,.2,.3,np.nan], 'Eular[2]': [.01,.02,.03,.04],
          'AngRate[1]': [1,2,3,4], 'AngRate[2]': [0,0,0,0], 'AngRate[3]': [0,0,0,0],
          'fault_state': [0,1,1,1]})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'state.xlsx'
            frame.to_excel(path,index=False)
            actual = endpoints_from_xlsx(path, 2.0)
        self.assertEqual(actual['window_end_index'].tolist(), [1,3])
        self.assertEqual(actual['speed_3d__last'].tolist(),[2,3])
        self.assertEqual(actual['roll__last'].tolist(),[.2,.3])
        self.assertEqual(actual['altitude_estimated__last'].tolist(),[2,3])

if __name__ == '__main__': unittest.main()
