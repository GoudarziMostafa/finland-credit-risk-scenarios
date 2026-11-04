export function calculate(exposures, scenario, options = {}) {
  const {pd = 0.015, lgd = 0.4, severity = 1} = options;
  for (const [name, value, max] of [["pd",pd,1],["lgd",lgd,1],["severity",severity,2]]) {
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > max) throw new Error("Invalid " + name);
  }
  if (!Array.isArray(exposures) || !exposures.length) throw new Error("Missing exposures");
  const seen = new Set();
  const rows = exposures.map(e => {
    if (seen.has(e.sector)) throw new Error("Duplicate sector"); seen.add(e.sector);
    if (typeof e.exposure_eur !== "number" || !Number.isFinite(e.exposure_eur) || e.exposure_eur < 0) throw new Error("Invalid exposure");
    const a = scenario.sectors[e.sector];
    if (!a || !Number.isFinite(a.adverse_pd_multiplier) || a.adverse_pd_multiplier < 1 || !Number.isFinite(a.adverse_lgd_uplift) || a.adverse_lgd_uplift < 0) throw new Error("Invalid stress assumptions");
    const rawPd = pd * (1 + severity * (a.adverse_pd_multiplier - 1));
    const rawLgd = lgd + severity * a.adverse_lgd_uplift;
    const adversePd = Math.min(1, rawPd), adverseLgd = Math.min(1, rawLgd);
    const baseline = e.exposure_eur * pd * lgd, adverse = e.exposure_eur * adversePd * adverseLgd;
    return {sector:e.sector, exposure:e.exposure_eur, pd, lgd, adversePd, adverseLgd, baseline, adverse, change:adverse-baseline, pdCapped:rawPd>1, lgdCapped:rawLgd>1};
  });
  const totals = rows.reduce((t,r) => ({exposure:t.exposure+r.exposure, baseline:t.baseline+r.baseline, adverse:t.adverse+r.adverse, change:t.change+r.change, pdCaps:t.pdCaps+Number(r.pdCapped), lgdCaps:t.lgdCaps+Number(r.lgdCapped)}), {exposure:0,baseline:0,adverse:0,change:0,pdCaps:0,lgdCaps:0});
  return {rows,totals};
}
