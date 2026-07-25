<template>
  <div class="rp-paper">
    <template v-for="(sec, i) in (model?.sections || [])" :key="i">
      <!-- Cover -->
      <div v-if="sec.kind === 'cover'" class="rp-cover">
        <h1 class="rp-cover-title">{{ sec.title }}</h1>
        <div class="rp-cover-sub">{{ sec.subtitle }}</div>
        <div class="rp-cover-city">{{ sec.city }}</div>
        <div class="rp-cover-aud">Prepared for: {{ sec.audience }}</div>
        <div class="rp-ctrl">
          Document ID {{ model.meta.doc_id }} · Generated {{ shortDate(model.meta.generated_utc) }}<br>
          Tool release {{ model.meta.tool_release }} · Content SHA-256 {{ model.meta.content_sha256 }}
        </div>
      </div>

      <!-- Provenance summary -->
      <section v-else-if="sec.kind === 'provenance_summary'">
        <h2 class="rp-h">{{ sec.title }}</h2>
        <p class="rp-lead">{{ sec.headline }}</p>
        <table class="rp-table">
          <thead><tr><th>Source</th><th>Count</th><th>Origin</th></tr></thead>
          <tbody>
            <tr v-for="(r, j) in sec.rows" :key="j">
              <td>{{ r.source }}</td><td>{{ r.count }}</td>
              <td>
                <span class="rp-chip" :class="r.discovered ? 'rp-chip-disc' : 'rp-chip-decl'">
                  {{ r.discovered ? 'Discovered' : 'Declared' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Executive / compliance detail (fact lists) -->
      <section v-else-if="sec.kind === 'exec_status' || sec.kind === 'compliance_detail'">
        <h2 class="rp-h">{{ sec.title }}</h2>
        <dl class="rp-kv">
          <template v-for="(f, j) in sec.facts" :key="j">
            <dt>{{ f.label }}</dt><dd>{{ f.value }}</dd>
          </template>
        </dl>
        <p v-if="sec.background" class="rp-body">{{ sec.background }}</p>
        <p v-if="sec.note" class="rp-note">{{ sec.note }}</p>
        <p v-if="sec.notice" class="rp-note">{{ sec.notice }}</p>
      </section>

      <!-- Asset inventory -->
      <section v-else-if="sec.kind === 'asset_inventory'">
        <h2 class="rp-h">{{ sec.title }}</h2>
        <p class="rp-body">{{ sec.intro }}</p>
        <table v-if="sec.rows?.length" class="rp-table">
          <thead><tr><th>Vendor / System</th><th>Type</th><th>Source</th><th>Conf.</th><th>Status</th></tr></thead>
          <tbody>
            <tr v-for="(r, j) in sec.rows" :key="j">
              <td>{{ r.vendor }}</td><td>{{ r.type }}</td><td>{{ r.source }}</td>
              <td>{{ r.confidence }}</td><td>{{ r.status }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="rp-body">{{ sec.empty }}</p>
      </section>

      <!-- Violations / candidate findings -->
      <section v-else-if="sec.kind === 'violations'">
        <h2 class="rp-h">{{ sec.title }}</h2>
        <p v-if="!sec.items?.length" class="rp-body">{{ sec.empty }}</p>
        <template v-else>
          <p class="rp-body">{{ sec.intro }}</p>
          <div v-for="(v, j) in sec.items" :key="j" class="rp-finding">
            <h3 class="rp-h3">Finding {{ j + 1 }}: {{ v.rule_id }} — {{ v.citation }}</h3>
            <dl class="rp-kv">
              <dt>Severity</dt><dd>{{ v.severity }}</dd>
              <dt>Status</dt><dd>{{ v.status }}</dd>
              <dt>Cure deadline</dt><dd>{{ v.cure_deadline }}</dd>
              <template v-if="v.days_remaining != null"><dt>Days remaining</dt><dd>{{ v.days_remaining }}</dd></template>
              <template v-if="v.remediation"><dt>Remediation</dt><dd>{{ v.remediation }}</dd></template>
            </dl>
          </div>
        </template>
      </section>

      <!-- Recommendations -->
      <section v-else-if="sec.kind === 'recommendations'">
        <h2 class="rp-h">{{ sec.title }}</h2>
        <ul class="rp-list"><li v-for="(it, j) in sec.items" :key="j">{{ it }}</li></ul>
      </section>

      <!-- Statutory reference -->
      <section v-else-if="sec.kind === 'statutory_reference'">
        <h2 class="rp-h">{{ sec.title }}</h2>
        <dl class="rp-kv">
          <template v-for="(it, j) in sec.items" :key="j"><dt>{{ it.citation }}</dt><dd>{{ it.text }}</dd></template>
        </dl>
      </section>

      <!-- Methodology -->
      <section v-else-if="sec.kind === 'methodology'">
        <h2 class="rp-h">{{ sec.title }}</h2>
        <p v-for="(p, j) in sec.paragraphs" :key="j" class="rp-body">{{ p }}</p>
      </section>

      <!-- Attestation -->
      <section v-else-if="sec.kind === 'attestation'">
        <h2 class="rp-h">{{ sec.title }}</h2>
        <p class="rp-body">{{ sec.statement }}</p>
        <div v-for="(f, j) in sec.fields" :key="j" class="rp-sign">
          <span class="rp-sign-label">{{ f }}:</span><span class="rp-sign-line"></span>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup>
/**
 * ReportPreview — renders a BundleModel as on-brand HTML.
 *
 * Presentational only (no store, no service), per the layering rule. It renders the
 * SAME model the backend renders to PDF/DOCX, so the preview a user approves is exactly
 * what they download. This is the "wow" of the Reports section: a live, executive-grade
 * proof before a single file is generated.
 */
defineProps({ model: { type: Object, default: null } })

function shortDate(iso) {
  if (!iso) return ''
  try { return new Date(iso).toLocaleString() } catch { return iso }
}
</script>

<style scoped>
.rp-paper {
  background: #fff; color: #37474F; border-radius: 8px;
  padding: 40px 46px; box-shadow: 0 2px 14px rgba(0,0,0,0.10);
  font-family: Georgia, 'Times New Roman', serif; line-height: 1.5; max-width: 760px; margin: 0 auto;
}
.rp-cover { text-align: center; padding: 40px 0 28px; border-bottom: 1px solid #E4E9EF; margin-bottom: 26px; }
.rp-cover-title { color: #1565C0; font-size: 30px; margin: 0 0 10px; font-weight: 700; }
.rp-cover-sub { color: #37474F; font-size: 13px; }
.rp-cover-city { color: #263238; font-size: 20px; font-weight: 700; margin: 22px 0 6px; }
.rp-cover-aud { color: #6B7280; font-size: 12px; margin-bottom: 26px; }
.rp-ctrl { color: #90A0AE; font-size: 9.5px; font-family: 'Courier New', monospace; line-height: 1.7; word-break: break-all; }
.rp-h { color: #1565C0; font-size: 16px; margin: 26px 0 8px; font-family: Helvetica, Arial, sans-serif; }
.rp-h3 { color: #263238; font-size: 13px; margin: 12px 0 4px; font-family: Helvetica, Arial, sans-serif; }
.rp-lead { font-weight: 700; font-size: 14px; color: #263238; margin: 0 0 12px; }
.rp-body { font-size: 12.5px; margin: 6px 0; }
.rp-note { font-size: 10.5px; color: #90A0AE; font-style: italic; margin: 8px 0; }
.rp-table { width: 100%; border-collapse: collapse; margin: 10px 0; font-family: Helvetica, Arial, sans-serif; }
.rp-table th { background: #1565C0; color: #fff; text-align: left; padding: 7px 9px; font-size: 11px; }
.rp-table td { padding: 6px 9px; font-size: 11.5px; border: 1px solid #E4E9EF; }
.rp-table tbody tr:nth-child(even) { background: #F5F7FA; }
.rp-chip { padding: 1px 8px; border-radius: 10px; font-size: 10px; font-weight: 700; }
.rp-chip-disc { background: #E3F2FD; color: #1565C0; }
.rp-chip-decl { background: #ECEFF1; color: #546E7A; }
.rp-kv { display: grid; grid-template-columns: 190px 1fr; gap: 3px 12px; margin: 8px 0; font-family: Helvetica, Arial, sans-serif; font-size: 11.5px; }
.rp-kv dt { font-weight: 700; color: #263238; }
.rp-kv dd { margin: 0; }
.rp-list { font-size: 12.5px; }
.rp-finding { border-left: 3px solid #1565C0; padding-left: 12px; margin: 10px 0; }
.rp-sign { display: flex; align-items: flex-end; gap: 8px; margin: 14px 0; font-family: Helvetica, Arial, sans-serif; font-size: 11.5px; }
.rp-sign-label { font-weight: 700; white-space: nowrap; }
.rp-sign-line { flex: 1; border-bottom: 1px solid #90A0AE; height: 14px; }
</style>
