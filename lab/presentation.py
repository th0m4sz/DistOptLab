# Función de este módulo: Comparte estilos y ayudas visuales sin intervenir en el cálculo ni en los datos.
"""Jerarquía, espaciado y divulgación de información secundaria de la interfaz."""
from nicegui import ui


def help_details(title, text):
    with ui.expansion(title, icon='help_outline').classes('help-details w-full') as expansion:
        ui.label(text).classes('help-copy')
    return expansion


def section_heading(number, title):
    with ui.row().classes('section-heading w-full items-center gap-3'):
        ui.label(str(number).zfill(2)).classes('step-index').props('aria-hidden=true')
        ui.label(title).classes('section-title').props('role=heading aria-level=2')


VISUAL_CSS = '''
:root{--lab-ink:#20384b;--lab-muted:#526678;--lab-line:#dce5eb;--lab-accent:#087f8c;--lab-soft:#eef7f7}
body{background:#f3f6f9;color:var(--lab-ink);font-size:14px}
.page-wrap{max-width:1320px;padding:26px 32px 48px;gap:22px}
.lab-header{min-height:62px;padding:12px 32px!important}
.brand{font-size:18px;letter-spacing:-.4px}.brand-mark{background:#e6f3f3;border-radius:11px;padding:7px;box-sizing:content-box}
.header-context{font-size:12px;color:var(--lab-muted);display:flex;align-items:center;gap:8px}
.header-context:before{content:'';width:7px;height:7px;background:#21836a;border-radius:50%}
.hero-title{font-size:29px;line-height:1.2;letter-spacing:-.8px}.eyebrow{color:#526678;font-size:10px;letter-spacing:1.4px}
.muted{color:var(--lab-muted);font-size:13px;line-height:1.6}
.q-card{border:1px solid var(--lab-line);border-radius:16px;box-shadow:0 3px 14px #20384b05;padding:24px}
.section-title{font-size:17px;line-height:1.35;font-weight:650;letter-spacing:-.25px}
.section-heading{margin-bottom:5px}.step-index{width:33px;height:33px;display:grid;place-items:center;border-radius:10px;background:#e7f3f4;color:#086773;font-size:13px;font-weight:750;flex-shrink:0}
.main-tabs{padding:6px;background:#e7edf2;border:1px solid #dfe7ed;border-radius:13px}
.main-tabs .q-tab{min-height:44px;font-size:14px;border-radius:9px;color:#526678;flex:1;padding:0 16px}
.main-tabs .q-tab--active{background:#fff;color:#086773;box-shadow:0 2px 6px #20384b12;font-weight:700}
.main-tabs .q-tab__indicator{display:none}.main-tabs .q-tab__icon{font-size:21px}.main-tabs .q-tab__label{font-size:14px}
.q-btn{font-size:13px;min-height:38px;border-radius:9px;letter-spacing:0}
.q-btn--unelevated{box-shadow:0 2px 4px #075e6712}.q-btn--outline:before{border-color:#b9ccd3}
.q-btn:focus-visible,.q-tab:focus-visible,.q-item:focus-visible{outline:3px solid #116ca4;outline-offset:3px}
.q-field--outlined .q-field__control{border-radius:9px;background:#fff}
.q-field--outlined .q-field__control:before{border-color:#bdcbd6}
.q-field__label{color:#526678}.q-field__native{color:#20384b}
.q-field--disabled .q-field__control{background:#f1f4f6}
.nicegui-expansion{border:1px solid var(--lab-line);border-radius:10px;overflow:hidden;background:#fff}
.nicegui-expansion>.q-expansion-item__container>.q-item{min-height:45px;padding:10px 13px}
.nicegui-expansion>.q-expansion-item__container>.q-item .q-item__section--avatar{min-width:30px;color:#537887}
.nicegui-expansion .q-expansion-item__content>.nicegui-column{padding:14px;gap:12px}
.help-details{border:0!important;background:#f5f8fa!important;border-radius:9px}
.help-details>.q-expansion-item__container>.q-item{min-height:38px;font-size:12px;color:#3d5e70}
.help-details .help-copy{padding:0 14px 14px;font-size:13px;line-height:1.65;color:var(--lab-muted);white-space:pre-line}
.help-details .q-expansion-item__content{padding:0!important}
.note{background:#f0f6f8;color:#3d5e70;border:1px solid #e0ebef;border-left:3px solid #a1c8cf;border-radius:9px;padding:11px 14px;font-size:13px;line-height:1.6}
.guide-banner{padding:18px 22px;background:#fff;border-left:4px solid #087f8c;gap:12px}
.guide-banner .guide-icon{color:#087f8c;background:#edf7f7;padding:10px;border-radius:12px;box-sizing:content-box}
.experiment-layout{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:24px;align-items:start;width:100%}
.experiment-main,.experiment-aside{min-width:0;width:100%}.experiment-aside{position:sticky;top:86px}
.experiment-aside .q-card{padding:20px;background:#fafdfe}.experiment-aside .metric-value{font-size:25px}
.field-group-label{font-size:11px;letter-spacing:.8px;text-transform:uppercase;color:#526678;font-weight:700;margin-top:6px}
.agent-card{background:#f7f9fb!important;padding:16px;box-shadow:none;border-radius:11px}
.actions-strip{padding-top:16px;margin-top:4px;border-top:1px solid var(--lab-line)}
.chart-card{padding:18px;background:#fff;border:1px solid #d7e3e9;box-shadow:none}
.chart-controls{background:#f5f8fa;padding:12px;border-radius:10px}
.run-status{font-size:15px;font-weight:650;color:#20384b;padding:4px 0}
.context-line{background:#f6f9fb;color:#486275;border:1px solid #e1e9ef;padding:9px 12px;border-radius:8px;font-size:12px;line-height:1.5}
.error-note{border-left-color:#b43c45;background:#fff3f3;color:#8e2930}
.q-table th{font-size:12px;font-weight:700;color:#526678;background:#f1f5f8;padding:13px 16px}
.q-table td{font-size:13px;padding:13px 16px}.q-table tbody tr:nth-child(even){background:#fafcfd}
.q-table tbody tr:hover{background:#eef6f8}.q-table__container{border-radius:11px}
.history-table table{table-layout:fixed;width:100%;min-width:950px}
.history-table th,.history-table td{white-space:normal;overflow-wrap:anywhere;padding:12px}
.history-table th:nth-child(1){width:4%}.history-table th:nth-child(2){width:24%}.history-table th:nth-child(3){width:19%}
.history-table th:nth-child(4){width:7%}.history-table th:nth-child(5){width:9%}.history-table th:nth-child(6){width:15%}
.history-table th:nth-child(7){width:10%}.history-table th:nth-child(8){width:12%}
.q-footer{font-size:11px;min-height:28px;background:#fff!important}
.algorithm-designer{border-radius:16px!important}.algorithm-designer>.nicegui-row:first-child{padding:0 4px 8px;border-bottom:1px solid var(--lab-line)}
.algorithm-designer .q-tabs{background:#f1f5f8;border:0;border-radius:9px;padding:4px}
.algorithm-designer .q-tab{border-radius:6px;padding:0 15px;min-height:38px;color:#526678}
.algorithm-designer .q-tab--active{background:#fff;color:#086773;box-shadow:0 1px 4px #20384b17;font-weight:700}
.algorithm-designer .q-tab__indicator{display:none}.algorithm-designer .q-tab-panel{padding:18px 8px}
.algorithm-designer .editor-row{background:#f8fafc!important;border:1px solid #dce5eb;border-left:3px solid #9bbdc6;box-shadow:none;padding:18px}
.algorithm-designer .rule-help{font-size:12px;line-height:1.6;color:#486275;background:#ecf3f6;padding:9px 12px;border-radius:7px}
.algorithm-designer .editor-footer{background:#fff;padding:10px 4px 0}.algorithm-designer .muted{font-size:13px}
.algorithm-designer .q-btn--dense{min-height:32px}
@media(max-width:1100px){.experiment-layout{grid-template-columns:minmax(0,1fr)}.experiment-aside{position:static;display:grid;grid-template-columns:1fr 1fr;gap:16px}.experiment-aside .q-card{margin-top:0!important;height:100%}}
@media(max-width:700px){.page-wrap{padding:18px 14px 44px}.q-card{padding:18px}.lab-header{padding:10px 16px!important}.hero-title{font-size:25px}.header-context{display:none}.main-tabs .q-tab{min-width:90px;padding:0 10px}.main-tabs .q-tab__label{font-size:12px}.experiment-aside{display:flex}.guide-banner{padding:16px}.guide-banner .guide-icon{display:none}.chart-controls{padding:10px}.brand{font-size:16px}}
@media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;transition-duration:0s!important;animation-duration:0s!important}}
'''
