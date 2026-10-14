# Exact external inputs and acquisition

Default reproduction never downloads flight archives. Optional raw reproduction
uses explicitly supplied archives and the bundled versioned adapters.

1. RflyMAD HIL: https://www.kaggle.com/datasets/xianglile/rflymad-hil,
   **dataset version 2**. This frozen intake contains 2,613 cases with TestInfo,
   TrueState and UAVState files, rather than the count on a changing overview
   page. The published receipt pins every consumed UAVState workbook SHA.
   Official project and use conditions:
   https://rfly-openha.github.io/documents/4_resources/dataset.html.
   Original archives and window telemetry are not redistributed here.
2. RflyMAD real: obtain **Real-Motor.zip** from that official page. The exact
   SHA is 77161c06b2c27b0827e253f4b0bdd36bb5074414e8d235da0a5b7f6aa01efab6
   (5,982,544,439 bytes). The 406 cases use estimator-local-position, vehicle
   attitude/angular-rate and control timestamp bounds; 407_1 uses the original
   vehicle-local-position member and its separate quaternion adapter. The
   20-Hz causal held grid is confined to this sampled-point profile.
3. PX4 Flight Review: https://review.px4.io/plot_app?log=0000c079-6820-409a-95da-e86358b6c20f.
   Download that ULog; required SHA is
   63482730793be48ffa782274dadb0ac65dcb038b7b163f9e0df1cce7f45441ff.
   Per-log redistribution conditions remain unresolved, so it stays upstream.
4. IDF_DS v1.0: https://doi.org/10.5281/zenodo.16992976,
   Holybro Pixhawk.zip MD5 8b990cc4c7ec1225a16e9a28225e5162.
   The three complete lap_120 members are supplied under the record's verified
   CC BY 4.0 license with attribution in `data/external/idf_ds_lap120_verified_v34`.
   v33 retained two truncated member tails. Its hashes and results are historical;
   current results use the verified full members and explicitly compare that
   correction. Do not silently call the old inputs complete official exports.
5. INSANE indoor_1: https://www.aau.at/en/smart-systems-technologies/control-of-networked-systems/datasets/insane-dataset/.
   Obtain https://cns-data.aau.at/insane-dataset/indoor_1_sensors.zip and
   https://cns-data.aau.at/insane-dataset/insane_sensor_calib_preprocessed.zip.
   The preparation script retains the exact local ZIP header and compressed
   px4_imu member, verifies its segment SHA/CRC, and verifies the calibration
   archive SHA. The source page states a noncommercial restriction; these
   archives and their telemetry are not redistributed here.

Install the optional existing-runtime requirements with
`python -m pip install -r requirements-replay.txt`. `prepare_external_inputs.py`
accepts the local archive/ULog paths and a new output directory. It extracts only
the declared members, verifies their hashes, and never changes the supplied
archives. Copying Real-Motor.zip needs about 6 GB of additional space;
`--omit-real-archive-copy` prepares only the two 406 cases and leaves the 407
archive placement explicit. Its receipt identifies any omitted inputs.

```sh
python research/real_replay/prepare_external_inputs.py --output EXTERNAL_ROOT --rfly-real-archive REAL_MOTOR_ZIP --hil-archive HIL_V2_ZIP --insane-sensors-archive INSANE_SENSORS_ZIP --insane-calibration-archive INSANE_CALIBRATION_ZIP --flight-review-ulog FLIGHT_REVIEW_ULOG
python research/threshold_reproduction/reproduce_thresholds.py --raw-state-root EXTERNAL_ROOT/external_datasets/rflymad/HIL-Complete-StateOnly --reference-split research/threshold_reproduction/frozen_case_split.csv --workers 1 --output NEW_THRESHOLD_RUN
python research/real_replay/reproduce_real_replays.py --input-root EXTERNAL_ROOT --output NEW_REPLAY_RUN
```

The replay receipt distinguishes the six derived observation files, 68
formula--trace evaluations and event rows. Native profiles remain separate and
have no held-value alignment. The original 28,210-event regression concerns the
retained v33 inputs. The corrected IDF replay is reported separately and does
not overwrite that regression. Hash mismatches are version/acquisition errors;
they are never repaired by replacing the baseline or ignoring the mismatch.
