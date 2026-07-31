// ── Palette ────────────────────────────────────────────────────────────────
export const COLORS = {
  personal: '#2563eb',
  itaas:    '#7c3aed',
  cmse:     '#059669',
  mib:      '#0284c7',
  aws:      '#d97706',
  ext:      '#dc2626',
}

// ── Helpers ────────────────────────────────────────────────────────────────
const svc = (id, label, sub, platform, x, y, extra = {}) => ({
  id,
  type: 'serviceNode',
  position: { x, y },
  data: { label, sub, platform, color: COLORS[platform], ...extra },
})

const grp = (id, label, platform, x, y, w, h) => ({
  id,
  type: 'groupNode',
  position: { x, y },
  style: { width: w, height: h },
  data: { label, color: COLORS[platform] },
  selectable: false,
  focusable: false,
})

const edge = (id, source, target, label, type = 'rest') => ({
  id,
  source,
  target,
  label,
  type: 'smoothstep',
  animated: type === 'stream',
  style: {
    stroke: type === 'soap'   ? COLORS.ext
          : type === 'oidc'   ? COLORS.itaas
          : type === 'aws'    ? COLORS.aws
          : type === 'redis'  ? COLORS.aws
          : '#94a3b8',
    strokeWidth: 1.5,
    strokeDasharray: type === 'oidc' || type === 'soap' ? '5 4' : undefined,
  },
  labelStyle: { fill: '#64748b', fontSize: 9, fontFamily: 'Inter, sans-serif' },
  labelBgStyle: { fill: '#f8fafc', fillOpacity: 0.85 },
  markerEnd: {
    type: 'arrowclosed',
    width: 12, height: 12,
    color: type === 'soap'  ? COLORS.ext
         : type === 'oidc'  ? COLORS.itaas
         : type === 'aws'   ? COLORS.aws
         : type === 'redis' ? COLORS.aws
         : '#94a3b8',
  },
})

// ── Nodes ──────────────────────────────────────────────────────────────────
//
// Layout (canvas px, no parent-child — free to rearrange):
//
//  ┌─ Personal (us-east-1) ──┐  ┌─ ITaaS Shared ──┐  ┌─ External BSS ──┐
//  │                          │  │                  │  │                 │
//  └──────────────────────────┘  └──────────────────┘  └─────────────────┘
//  ┌─ AWS Managed ────────────────────────────────────────────────────────┐
//  └──────────────────────────────────────────────────────────────────────┘
//  ┌─ CMSE · eu-west-1 (isolated, own AWS account) ──┐  ┌─ MIB/DMM ────┐
//  └──────────────────────────────────────────────────┘  └──────────────┘

export const initialNodes = [
  // ── Group backgrounds (rendered first so they sit behind service nodes) ─
  grp('g-personal', 'Personal Platform · us-east-1 · AWS 469793732550', 'personal',  30,  30, 640, 460),
  grp('g-itaas',    'ITaaS Shared Services',                             'itaas',    710,  30, 400, 320),
  grp('g-ext',      'External BSS & Partners',                           'ext',     1150,  30, 280, 580),
  grp('g-aws',      'AWS Managed · us-east-1',                           'aws',       30, 520, 680, 160),
  grp('g-cmse',     'CMSE Content Platform · eu-west-1 · AWS 211125718407 (isolated)', 'cmse', 30, 720, 680, 240),
  grp('g-mib',      'MIB / DMM CMS · eu-west-1 · AWS 211125718407',      'mib',     750, 720, 470, 240),

  // ── Personal Platform ──────────────────────────────────────────────────
  svc('beethoven',     'beethoven',       'BFF · Node.js · 2 tasks · :8086',    'personal',  220, 120),
  svc('backoffice',    'backoffice',      'Admin UI · Node.js · 2 tasks',        'personal',   60,  80),
  svc('notification',  'notification-api','Notifications · Node.js',             'personal',  430,  80),
  svc('billing_proxy', 'billing-proxy',   'BSS Adapter · Node.js · 2t · :8088', 'personal',   60, 280),
  svc('purchase_sl',   'purchase-sl',     'Purchase SL · Node.js · 2t · :8087', 'personal',  430, 280),
  svc('wurfl',         'wurfl-api',       'Device Detection (WURFL)',            'personal',  220, 370),

  // ── ITaaS Shared (same AWS account as Personal) ────────────────────────
  svc('wallstreet',  'wallstreet',   'Billing Ledger · Node.js',  'itaas',  730, 100),
  svc('godfather',   'godfather',    'Auth / Identity · Postgres', 'itaas',  730, 230),
  svc('startrek',    'startrek',     'Content Entitlements',       'itaas',  970, 100),
  svc('content_api', 'content-api',  'Content Catalog API',        'itaas',  970, 230),

  // ── External BSS / Partners ────────────────────────────────────────────
  svc('mcss',   'MCSS BSS',      'pedidosvas2.personal.com.ar\nSOAP/XML → REST', 'ext', 1175,  70),
  svc('sso',    'Telecom SSO',   'sso.telecom.com.ar · OIDC/JWKS',               'ext', 1175, 210),
  svc('som',    'SOM',           'Service Order Management · REST',               'ext', 1175, 350),
  svc('disney', 'Disney+',       'Content Partner · REST/JSON',                   'ext', 1175, 470),

  // ── AWS Managed ────────────────────────────────────────────────────────
  svc('redis',      'Redis',      'notify.redis.production · :6379',  'aws',   50, 575),
  svc('sqs',        'SQS',        'recharge-notification-prod',        'aws',  225, 575),
  svc('firehose',   'Firehose',   'reports · providers-reports',       'aws',  410, 575),
  svc('cloudfront', 'CloudFront', 'cdn-production.personal-svcs.com', 'aws',  575, 575),

  // ── CMSE — isolated, separate AWS account ─────────────────────────────
  svc('cmse_api',       'cmse-api',         'Content API · eu-west-1',  'cmse',   50, 790),
  svc('cmse_feeder',    'cmse-feeder',       'Ingest Worker',             'cmse',  230, 790),
  svc('cmse_scheduler', 'cmse-scheduler',    'Scheduling Worker',         'cmse',  430, 790),
  svc('cmse_matcher',   'cmse-matcher',      'Content Matcher',           'cmse',  230, 890),
  svc('cmse_tmdb',      'tmdb-connector',    'TMDB Metadata Ingest',      'cmse',  430, 890),
  svc('cmse_rightv',    'rightv-connector',  'Rights Verification',       'cmse',   50, 890),

  // CMSE external targets (positioned just outside the CMSE group)
  svc('tmdb',   'TMDB',          'api.themoviedb.org · REST/JSON', 'ext', 750, 800),
  svc('rightv', 'RightsVision',  'Rights Management API · REST',   'ext', 750, 900),

  // ── MIB / DMM CMS ─────────────────────────────────────────────────────
  svc('mib_cms',   'mib-cms-api', 'CMS API · .NET',            'mib',  770, 790),
  svc('mib_auth',  'mib-auth',    'CMS Auth',                   'mib',  990, 790),
  svc('mib_front', 'mib-front',   'CMS Frontend',               'mib',  770, 890),
  svc('dmm_api',   'dmm-api',     'Digital Media Mgmt API',     'mib',  990, 890),
]

// ── Edges ──────────────────────────────────────────────────────────────────
// Only edges confirmed via Terraform env vars or GitHub code search.
// Uncertain links (Telecom AuthM test endpoint, Cablevision redirect) omitted.

export const initialEdges = [
  // backoffice → internal services (confirmed via env vars)
  edge('bo-beet',  'backoffice',    'beethoven',    'REST/JSON'),
  edge('bo-bp',    'backoffice',    'billing_proxy','REST/JSON'),
  edge('bo-psl',   'backoffice',    'purchase_sl',  'REST/JSON'),
  edge('bo-ws',    'backoffice',    'wallstreet',   'REST/JSON'),
  edge('bo-redis', 'backoffice',    'redis',        'Redis',   'redis'),
  edge('bo-cf',    'backoffice',    'cloudfront',   'Signed URL', 'aws'),

  // beethoven → dependencies (all confirmed via production.tfvars)
  edge('beet-bp',   'beethoven', 'billing_proxy', 'REST/JSON'),
  edge('beet-ws',   'beethoven', 'wallstreet',    'REST/JSON'),
  edge('beet-st',   'beethoven', 'startrek',      'REST/JSON'),
  edge('beet-ca',   'beethoven', 'content_api',   'REST/JSON'),
  edge('beet-gf',   'beethoven', 'godfather',     'REST/JSON'),
  edge('beet-notif','beethoven', 'notification',  'REST/JSON'),
  edge('beet-wurfl','beethoven', 'wurfl',         'REST/JSON'),
  edge('beet-redis','beethoven', 'redis',         'Redis',      'redis'),
  edge('beet-sqs',  'beethoven', 'sqs',           'AWS SDK',    'aws'),
  edge('beet-fh',   'beethoven', 'firehose',      'AWS SDK',    'stream'),
  edge('beet-cf',   'beethoven', 'cloudfront',    'Signed URL', 'aws'),
  edge('beet-sso',  'beethoven', 'sso',           'OIDC/JWKS',  'oidc'),

  // billing-proxy → MCSS BSS (confirmed: PERSONAL_BILLING_SERVICE_MCSS_URL)
  edge('bp-mcss', 'billing_proxy', 'mcss', 'SOAP/XML', 'soap'),

  // purchase-sl → external (confirmed: SOM retry config, Disney retry config, SSO URL)
  edge('psl-som',   'purchase_sl', 'som',    'REST/JSON'),
  edge('psl-dis',   'purchase_sl', 'disney', 'REST/JSON'),
  edge('psl-sso',   'purchase_sl', 'sso',    'OIDC',    'oidc'),
  edge('psl-sqs',   'purchase_sl', 'sqs',    'AWS SDK',  'aws'),

  // CMSE internal (confirmed: all in same cluster, worker→API pattern)
  edge('cf-ca',  'cmse_feeder',    'cmse_api', 'REST/JSON'),
  edge('cs-ca',  'cmse_scheduler', 'cmse_api', 'REST/JSON'),
  edge('cm-ca',  'cmse_matcher',   'cmse_api', 'REST/JSON'),

  // CMSE → external partners (confirmed: connector repos)
  edge('ct-tmdb',  'cmse_tmdb',   'tmdb',   'REST/JSON'),
  edge('cr-rightv','cmse_rightv', 'rightv', 'REST/JSON'),

  // MIB / DMM internal (confirmed: co-deployed in cmse-mib-fargate cluster)
  edge('dmm-mib', 'dmm_api',  'mib_cms',  'REST/JSON'),
  edge('mib-auth','mib_cms',  'mib_auth', 'REST/JWT', 'oidc'),
  edge('front-mib','mib_front','mib_cms', 'REST/JSON'),
]
