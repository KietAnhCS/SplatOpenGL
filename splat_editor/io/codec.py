SH_C0 = 0.28209479177387814
colors = 0.5 + SH_C0 * np.stack([col('f_dc'), col('f_dc_1'), col('f_dc_2')], axis=1)
alphas = 1.0 / (1.0 + np.exp(-col('opacity')))
scales = np.exp(np.stack([col('scale_0'), col('scale_1'), col('scale_2')], axis=1))
q = np.stack([col('rot_0'), col('rot_1'), col('rot_2'), col('rot_3')], axis=1)
length = np.linalg.norm(q, axis=1, keepdims=True)
q = q/ np.maximum(length, 1e-12)