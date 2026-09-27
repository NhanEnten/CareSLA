# AI input specification — `dilated_aug_s0_int8.tflite`

## Identity and status

- Canonical model: `dilated_aug_s0_int8.tflite`, **51,120 bytes**, SHA-256 `436a3463ee4802aa960c777775b680d3f9fc50a1c5798b0204a5c8c91dff0f11`.
- `model_data.cc` / `model_data.h` were generated from this exact file; a byte-for-byte round trip was checked. `model_data.cc` exports `g_dilated_aug_s0_model` and `g_dilated_aug_s0_model_len`.
- Training run: `kall-v2(1).ipynb`, configuration `dilated_aug`, seed `0`; 65 epochs; 20 training subjects, 6 validation, 6 held-out test subjects. Test metric at `p=0.7, N=2`: TP 445, FN 0, FP 23, TN 503 (per trial). This is **KFall test data**, not real ESP32 accuracy.

## IMU input and coordinate system

| Channel | Index | Expected unit | Conversion from MPU6050 signed raw reading |
| --- | ---: | --- | --- |
| AccX, AccY, AccZ | 0, 1, 2 | `g` | With `AFS_SEL=3` (±16 g): `raw / 2048.0f` |
| GyrX, GyrY, GyrZ | 3, 4, 5 | `degree/second` (°/s) | With `FS_SEL=3` (±2000 °/s): `raw / 16.4f` |

The KFall original sensor was an LPMS-B2 at the **lower back**, sampled at **100 Hz**. The source CSV columns were consumed directly as `AccX, AccY, AccZ, GyrX, GyrY, GyrZ`; the notebook does not rotate axes, change signs, convert units or use Euler angles. The axes are the **local sensor axes** in the original wearing arrangement; the source paper provides its Figure 1A showing the location and 3D coordinates. The exact board-to-body axis permutation/sign for the group's MPU6050 is **not measured**: P3 must mount the MPU6050 rigidly at the lower back, mark its orientation and compare a still standing reading with KFall (a large negative Y-axis acceleration, near zero X/Z and gyro). This statistical check is necessary but does not establish full dynamic axis equivalence. Do not hard-code an unmeasured rotation or claim the firmware axis alignment is verified.

MPU6050 scale factors above apply **only after configuring the corresponding full-scale registers**. If another range is selected, use its documented LSB-per-unit factor instead. Ensure acceleration includes gravity, is not converted to m/s², and angular velocity is not converted to rad/s. Calibrate gyro offset and confirm sensor mounting experimentally before interpreting field predictions.

## Tensor and preprocessing contract

- Input: `int8 [1, 50, 6]`, **NHWC-style time/channel order**: batch `[0]`, 50 time steps oldest to newest, 6 channels in the table's order. At 100 Hz the window spans 0.5 s. Run once per **10 new samples** (0.1 s). Do not reorder time or channels.
- For each raw physical sample `x[t,c]`, use training statistics in `dilated_aug_s0_input_spec.json`: `u = clamp((x - mean[c]) / std[c], -4.0, +4.0)`.
- Quantize with `q = clamp(round_to_nearest_even(u / 0.0313725508749485) - 1, -128, 127)` as `int8`. Input scale = `0.0313725508749485`; zero point = `-1`. Python's `np.rint` uses nearest even. A C implementation can use `nearbyintf` with the default `FE_TONEAREST`; compare the provided INT8 vectors after preprocessing.
- The firmware ring buffer should store 50 consecutive samples; every 10 new samples pack the chronological 50×6 block into the input tensor. The model expects consecutive, approximately evenly spaced measurements; check sampling jitter and dropped samples.

### Exact training normalization constants (order above)

| Channel | Mean | Std |
| --- | ---: | ---: |
| AccX | 0.021578215062618256 | 0.34529754519462585 |
| AccY | -0.7201448678970337 | 0.5091134905815125 |
| AccZ | -0.01292577013373375 | 0.5098982453346252 |
| GyrX | -0.7933411002159119 | 36.189029693603516 |
| GyrY | 7.5048747062683105 | 43.40152359008789 |
| GyrZ | -0.05011044815182686 | 21.957178115844727 |

## Output and decision rule

- Output: `int8 [1, 2]`, output scale `0.102272629737854`, zero point `-8`.
- **These are logits, not direct probabilities.** Index `0 = ADL/non-fall`, index `1 = FALL`. The Keras model's last layer is `Dense(2, activation=None)` and training uses `CategoricalCrossentropy(from_logits=True)`.
- Dequantize `logit[i] = (int(output[i]) - (-8)) * 0.102272629737854`. Margin `m = logit[1] - logit[0] = (int(output[1])-int(output[0])) * 0.102272629737854`. Probability `p_fall = sigmoid(m) = 1/(1+exp(-m))`.
- Notebook decision for each window: `m >= ln(0.7 / 0.3) ≈ 0.84729786`; raise candidate FALL only on **2 consecutive inference windows** meeting the threshold; otherwise reset the counter. The notebook's per-file metrics use this margin definition. INT8 outputs make threshold crossings discrete.
- This is a **pre-impact candidate** model; the CareSLA firmware's later immobility and 10-second cancellation stages must remain separate. The ~262 ms test lead time is not notification latency.

## Operators and firmware acceptance gate

Python LiteRT reported these builtin operator names: `ADD`, `BATCH_TO_SPACE_ND`, `CONCATENATION`, `CONV_2D`, `EXPAND_DIMS`, `FULLY_CONNECTED`, `MAX_POOL_2D`, `MEAN`, `MUL`, `REDUCE_MAX`, `RESHAPE`, `SPACE_TO_BATCH_ND`. Its displayed `DELEGATE` is a Python interpreter runtime optimization, not a builtin operator to register in TFLite Micro. Inspect the FlatBuffer's op versions and register matching kernels in the *installed* `esp-tflite-micro` component.

**Hardware support is not confirmed.** Success on Python LiteRT does not establish `esp-tflite-micro` support, successful `AllocateTensors()`, sufficient tensor arena, or acceptable ESP32 DevKit V1 latency. P3 must build against its pinned component, check `AllocateTensors()` and `Invoke()`, then compare golden input/output on the board; log arena used and invoke time. Report any unsupported op/version to P4 with the exact build/runtime error.

## Golden vectors

`golden_inputs_synthetic.json` and `golden_inputs.h` contain **10 deterministic synthetic diagnostic inputs**: five model-predicted FALL and five model-predicted ADL, each with a 50×6 INT8 input and exact expected INT8 logits from Python LiteRT. They verify byte order, op behavior and postprocessing; their categories are **model predictions, not ground-truth activity labels**. `generate_golden.py` regenerates them from this specific model SHA-256.

For ten **real labeled held-out KFall windows**, run `export_real_golden_kaggle.py` inside the still-live training notebook using `%run -i export_real_golden_kaggle.py`, then hand `golden_inputs_kfall_test.json` to P3. This file cannot be generated from the model alone; it requires the original held-out windows (`Xte`, `yte`, `idte`) absent from this ZIP.

## Source basis

- Original KFall paper: https://www.frontiersin.org/journals/aging-neuroscience/articles/10.3389/fnagi.2021.692865/full (experimental setup, sensor axes in Figure 1A, CSV units, 100 Hz).
- Original KFall dataset: https://sites.google.com/view/kfalldataset
- TDK MPU6000/6050 register map: https://invensense.tdk.com/wp-content/uploads/2015/02/MPU-6000-Register-Map.pdf (full-scale conversion constants).
