export const COLORS = {
  personal: '#2563eb',
  itaas:    '#7c3aed',
  kong:     '#d97706',
  cmse:     '#059669',
  mib:      '#0284c7',
  aws:      '#ea580c',
  ext:      '#dc2626',
  mgmt:     '#c026d3',
}

// ── Helpers ────────────────────────────────────────────────────────────────
const svc = (id, label, sub, platform, x, y, extra = {}) => ({
  id, type: 'serviceNode', position: { x, y },
  data: { label, sub, platform, color: COLORS[platform], ...extra },
})

const grp = (id, label, platform, x, y, w, h) => ({
  id, type: 'groupNode', position: { x, y },
  style: { width: w, height: h },
  data: { label, color: COLORS[platform] },
  selectable: false, focusable: false,
})

// edge type controls dash + color; animated = flowing dash on live routes
const edge = (id, source, target, label, type = 'rest', animated = true) => {
  const colors = {
    rest:  '#475569', kong:  '#f59e0b',
    soap:  '#ef4444', oidc:  '#8b5cf6',
    aws:   '#f97316', redis: '#f97316',
  }
  const dashes = { soap: '6 4', oidc: '6 4' }
  const color = colors[type] ?? colors.rest
  return {
    id, source, target, label,
    type: 'smoothstep', animated,
    style: {
      stroke: color, strokeWidth: 1.5,
      strokeDasharray: dashes[type],
    },
    labelStyle: { fill: '#64748b', fontSize: 9, fontFamily: 'Inter, sans-serif' },
    labelBgStyle: { fill: '#ffffff', fillOpacity: 0.9 },
    labelBgPadding: [3, 5],
    markerEnd: { type: 'arrowclosed', width: 10, height: 10, color },
  }
}

// ── Nodes ──────────────────────────────────────────────────────────────────
//
//  [Personal]  ──→  [Kong]  ──→  [ITaaS]  ──→  [External BSS]
//                                               [Mgmt Portal]
//  [AWS Managed]
//  [CMSE · isolated]           [MIB/DMM · isolated]

export const initialNodes = [
  // ── Group backgrounds ──────────────────────────────────────────────────
  grp('g-personal', 'Personal Platform · us-east-1 · AWS 469793732550', 'personal',  50,  50, 620, 430),
  grp('g-itaas',    'ITaaS Shared Services · AWS 469793732550',          'itaas',    890,  50, 450, 490),
  grp('g-ext',      'External BSS & Partners',                           'ext',     1420,  50, 270, 590),
  grp('g-aws',      'AWS Managed · us-east-1',                           'aws',       50, 560, 700, 150),
  grp('g-mgmt',     'Management Portal',                                  'mgmt',    1420, 700, 270, 195),
  grp('g-cmse',     'CMSE Content Pipeline · eu-west-1 · AWS 211125718407 (isolated)', 'cmse', 50, 790, 680, 220),
  grp('g-mib',      'MIB / DMM CMS · eu-west-1 · AWS 211125718407',      'mib',     800, 790, 490, 220),

  // ── Personal Platform ──────────────────────────────────────────────────
  svc('backoffice',    'backoffice',       'Admin UI · Node.js · 2t',         'personal',  70,  95),
  svc('beethoven',     'beethoven',        'BFF · Node.js · 2t · :8086',      'personal', 290, 150),
  svc('notification',  'notification-api', 'Notifications · Node.js',         'personal', 430,  95),
  svc('billing_proxy', 'billing-proxy',    'BSS Adapter · Node.js · 2t · :8088', 'personal', 70, 285),
  svc('purchase_sl',   'purchase-sl',      'Purchase SL · Node.js · 2t · :8087', 'personal', 390, 285),
  svc('wurfl',         'wurfl-api',        'Device Detection (WURFL)',         'personal', 235, 375),

  // ── Kong API Gateway (standalone — sits between Personal and ITaaS) ────
  {
    id: 'kong', type: 'kongNode', position: { x: 745, y: 215 },
    data: {
      label: 'Kong', sub: 'API Gateway',
      plugins: ['key-auth', 'acl', 'rate-limit'],
      upstreams: 5,
      color: COLORS.kong,
    },
  },

  // ── ITaaS Shared Services ──────────────────────────────────────────────
  svc('wallstreet',  'wallstreet',   'Billing Ledger · Node.js',              'itaas',  910, 100),
  svc('startrek',    'startrek',     'Content Entitlements',                  'itaas', 1130, 100),
  svc('swordfish',   'swordfish',    'Login / Password · Node.js → Postgres', 'itaas',  910, 245),
  svc('content_api', 'content-api',  'Content Catalog API',                   'itaas', 1130, 245),
  svc('godfather',   'godfather',    'Auth / Identity · Postgres',            'itaas',  910, 385),

  // ── External BSS / Partners ────────────────────────────────────────────
  svc('mcss',   'MCSS BSS',      'pedidosvas2.personal.com.ar\nSOAP/XML → REST', 'ext', 1440,  80),
  svc('sso',    'Telecom SSO',   'sso.telecom.com.ar · OIDC/JWKS',               'ext', 1440, 220),
  svc('som',    'SOM',           'Service Order Management',                      'ext', 1440, 355),
  svc('disney', 'Disney+',       'Content Partner · REST/JSON',                   'ext', 1440, 480),

  // ── Management Portal ──────────────────────────────────────────────────
  svc('mgmt_portal', 'agile-portal',  'Management Frontend · React',  'mgmt', 1440, 730),
  svc('keycloak',    'Keycloak',      'IAM · realm: management-portal\nEDITOR · ADMIN · QA_APPROVER', 'mgmt', 1440, 840),

  // ── AWS Managed ────────────────────────────────────────────────────────
  svc('redis',      'Redis',      'Cache · :6379',                    'aws',   70, 620),
  svc('sqs',        'SQS',        'recharge-notification-prod',       'aws',  250, 620),
  svc('firehose',   'Firehose',   'reports · providers-reports',      'aws',  440, 620),
  svc('cloudfront', 'CloudFront', 'CDN · cdn-production.personal-svcs.com', 'aws', 600, 620),

  // ── CMSE Content Pipeline (isolated) ──────────────────────────────────
  svc('cmse_api',       'cmse-api',        'Content API · eu-west-1', 'cmse',  70, 855),
  svc('cmse_feeder',    'cmse-feeder',      'Ingest Worker',           'cmse', 240, 855),
  svc('cmse_scheduler', 'cmse-scheduler',   'Scheduling Worker',       'cmse', 440, 855),
  svc('cmse_matcher',   'cmse-matcher',     'Content Matcher',         'cmse', 240, 950),
  svc('cmse_tmdb',      'tmdb-connector',   'TMDB Ingest',             'cmse', 440, 950),
  svc('cmse_rightv',    'rightv-connector', 'Rights Verification',     'cmse',  70, 950),

  // CMSE external targets (outside CMSE group)
  svc('tmdb',   'TMDB',         'api.themoviedb.org · REST/JSON', 'ext', 800, 855),
  svc('rightv', 'RightsVision', 'Rights Management API · REST',   'ext', 800, 950),

  // ── MIB / DMM CMS (co-deployed, eu-west-1) ────────────────────────────
  svc('mib_cms',   'mib-cms-api', 'CMS API · .NET',         'mib',  820, 855),
  svc('mib_auth',  'mib-auth',    'CMS Auth',                'mib', 1040, 855),
  svc('mib_front', 'mib-front',   'CMS Frontend',            'mib',  820, 950),
  svc('dmm_api',   'dmm-api',     'Digital Media Mgmt API',  'mib', 1040, 950),
]

// ── Edges ──────────────────────────────────────────────────────────────────
// Personal services → Kong → ITaaS (Kong is the authenticated gateway layer)
// Direct edges kept for non-Kong paths (BSS, AWS, SSO)

export const initialEdges = [
  // ── Through Kong ────────────────────────────────────────────────────────
  edge('beet-kong',   'beethoven',  'kong',       'via Kong',     'kong'),
  edge('bo-kong',     'backoffice', 'kong',       'via Kong',     'kong'),
  edge('kong-ws',     'kong',       'wallstreet', 'proxied REST', 'kong'),
  edge('kong-st',     'kong',       'startrek',   'proxied REST', 'kong'),
  edge('kong-sw',     'kong',       'swordfish',  'proxied REST', 'kong'),
  edge('kong-gf',     'kong',       'godfather',  'proxied REST', 'kong'),
  edge('kong-ca',     'kong',       'content_api','proxied REST', 'kong'),

  // ── Internal Personal (bypass Kong — same network) ────────────────────
  edge('beet-bp',     'beethoven',     'billing_proxy', 'REST', 'rest'),
  edge('beet-notif',  'beethoven',     'notification',  'REST', 'rest'),
  edge('beet-wurfl',  'beethoven',     'wurfl',         'REST', 'rest'),
  edge('bo-bp',       'backoffice',    'billing_proxy', 'REST', 'rest'),
  edge('bo-psl',      'backoffice',    'purchase_sl',   'REST', 'rest'),

  // ── AWS SDK calls ───────────────────────────────────────────────────────
  edge('beet-redis',  'beethoven',  'redis',      'Redis',   'redis', false),
  edge('beet-sqs',    'beethoven',  'sqs',        'AWS SDK', 'aws',   false),
  edge('beet-fh',     'beethoven',  'firehose',   'AWS SDK', 'aws',   false),
  edge('beet-cf',     'beethoven',  'cloudfront', 'CDN',     'aws',   false),
  edge('bo-redis',    'backoffice', 'redis',      'Redis',   'redis', false),
  edge('bo-cf',       'backoffice', 'cloudfront', 'CDN',     'aws',   false),
  edge('psl-sqs',     'purchase_sl','sqs',        'AWS SDK', 'aws',   false),

  // ── Auth (OIDC) ─────────────────────────────────────────────────────────
  edge('beet-sso',    'beethoven',  'sso', 'OIDC/JWKS', 'oidc', false),
  edge('psl-sso',     'purchase_sl','sso', 'OIDC',      'oidc', false),

  // ── External BSS ────────────────────────────────────────────────────────
  edge('bp-mcss',     'billing_proxy', 'mcss',   'SOAP/XML', 'soap', false),
  edge('psl-som',     'purchase_sl',   'som',    'REST',     'rest'),
  edge('psl-disney',  'purchase_sl',   'disney', 'REST',     'rest'),

  // ── Management Portal ───────────────────────────────────────────────────
  edge('portal-kc',   'mgmt_portal', 'keycloak', 'OIDC', 'oidc', false),

  // ── CMSE internal ───────────────────────────────────────────────────────
  edge('cf-ca',   'cmse_feeder',    'cmse_api', 'REST', 'rest'),
  edge('cs-ca',   'cmse_scheduler', 'cmse_api', 'REST', 'rest'),
  edge('cm-ca',   'cmse_matcher',   'cmse_api', 'REST', 'rest'),
  edge('ct-tmdb', 'cmse_tmdb',      'tmdb',     'REST', 'rest'),
  edge('cr-rv',   'cmse_rightv',    'rightv',   'REST', 'rest'),

  // ── MIB / DMM ───────────────────────────────────────────────────────────
  edge('dmm-mib',   'dmm_api',   'mib_cms',  'REST',     'rest'),
  edge('mib-auth',  'mib_cms',   'mib_auth', 'OIDC/JWT', 'oidc', false),
  edge('front-mib', 'mib_front', 'mib_cms',  'REST',     'rest'),
]
