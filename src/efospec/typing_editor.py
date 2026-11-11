"""Native, metadata-only host and redshift review panel."""
from copy import deepcopy
import json
from pathlib import Path
from PySide6 import QtWidgets as Q
from . import typing_metadata as metadata

TEXT_FIELDS = {
    'host_name': 'Host name', 'host_source': 'Host catalogue record / reference',
    'host_redshift': 'Host z', 'host_redshift_uncertainty': 'Host z uncertainty',
    'host_redshift_method': 'Host z method', 'host_reference_frame': 'Host z reference frame',
    'host_separation_arcsec': 'Host separation (arcsec)',
    'adopted_redshift': 'Adopted z', 'adopted_redshift_uncertainty': 'Adopted z uncertainty',
    'adopted_redshift_source': 'Adopted z reference', 'adopted_redshift_method': 'Adopted z method',
    'adopted_redshift_reference_frame': 'Adopted z reference frame',
    'spectrum_url': 'Original spectrum URL (if published)', 'tns_name': 'TNS name',
}
NUMERIC = {'host_redshift', 'host_redshift_uncertainty', 'host_separation_arcsec',
           'adopted_redshift', 'adopted_redshift_uncertainty'}


class TypingEditor(Q.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.run = None; self.document = None; self.index = -1; self.drafts = {}
        layout = Q.QVBoxLayout(self)
        self.spectra = Q.QComboBox(); self.spectra.setAccessibleName('Typing spectrum')
        layout.addWidget(self.spectra)
        self.binding = Q.QLabel('Open a completed reduction to review typing metadata.'); self.binding.setWordWrap(True)
        layout.addWidget(self.binding)
        scroll = Q.QScrollArea(); scroll.setWidgetResizable(True); layout.addWidget(scroll, 1)
        body = Q.QWidget(); scroll.setWidget(body); columns = Q.QHBoxLayout(body)
        form = Q.QFormLayout(); columns.addLayout(form, 1); self.fields = {}
        for key, title in TEXT_FIELDS.items():
            field = Q.QLineEdit(); field.setAccessibleName(title); form.addRow(title, field); self.fields[key] = field
        for key, title, choices in (
            ('host_status', 'Host association status', metadata.STATUSES),
            ('redshift_status', 'Redshift status', metadata.STATUSES),
            ('adopted_redshift_kind', 'Adopted z source kind', ('',)+metadata.KINDS)):
            field = Q.QComboBox(); field.addItems(choices); field.setAccessibleName(title)
            self.fields[key] = field; form.addRow(title, field)
        evidence = Q.QVBoxLayout(); columns.addLayout(evidence, 1)
        evidence.addWidget(Q.QLabel('Candidate galaxies (JSON list; all catalogue fields retained)'))
        self.candidates = Q.QPlainTextEdit(); self.candidates.setAccessibleName('Candidate galaxies JSON')
        evidence.addWidget(self.candidates)
        evidence.addWidget(Q.QLabel('Provenance (JSON list of references / measurements)'))
        self.provenance = Q.QPlainTextEdit(); self.provenance.setAccessibleName('Typing provenance JSON')
        evidence.addWidget(self.provenance)
        self.review_info = Q.QLabel(); self.review_info.setWordWrap(True); evidence.addWidget(self.review_info)
        evidence.addWidget(Q.QLabel('No candidate is automatically accepted.\nAn adopted z requires explicit acceptance.'))
        self.reviewer = Q.QLineEdit(); self.reviewer.setPlaceholderText('Reviewer identity'); self.reviewer.setAccessibleName('Typing reviewer')
        layout.addWidget(self.reviewer)
        self.accept_host = Q.QCheckBox('I accept this host association')
        self.accept_redshift = Q.QCheckBox('I accept this adopted redshift for future typing runs')
        layout.addWidget(self.accept_host); layout.addWidget(self.accept_redshift)
        buttons = Q.QHBoxLayout(); layout.addLayout(buttons)
        self.save_button = Q.QPushButton('Save metadata revision'); buttons.addWidget(self.save_button)
        self.reload_button = Q.QPushButton('Reload saved metadata'); buttons.addWidget(self.reload_button)
        self.report_button = Q.QPushButton('Refresh nightly HTML'); buttons.addWidget(self.report_button)
        self.report_button.clicked.connect(self.refresh_report)
        self.notice = Q.QLabel(); self.notice.setWordWrap(True); layout.addWidget(self.notice)
        self.save_button.clicked.connect(self.save); self.reload_button.clicked.connect(lambda:self.open_run(self.run))
        self.spectra.currentIndexChanged.connect(self.select)
        self.setEnabled(False)

    def open_run(self, run):
        self.run = Path(run); self.setEnabled(False); self.index = -1; self.drafts = {}
        self.spectra.blockSignals(True); self.spectra.clear()
        try:
            self.document = metadata.load(run) or metadata.skeleton(run)
            for record in self.document['spectra']:
                self.spectra.addItem(record['object_id']+' · '+Path(record['path']).name)
            self.binding.setText('Reduction: '+str(self.run)+'\nSHA256: '+self.document['reduction_manifest_sha256'])
            self.setEnabled(bool(self.document['spectra']))
            self.notice.setText('Metadata edits preserve spectra and do not run reduction or classification.')
        except (OSError, ValueError, KeyError) as exc:
            self.document = None; self.notice.setText(str(exc))
        finally:
            self.spectra.blockSignals(False)
        if self.document and self.document['spectra']: self.select(0)

    def capture(self):
        return dict(fields={k:(v.currentText() if isinstance(v, Q.QComboBox) else v.text()) for k,v in self.fields.items()},
                    candidates=self.candidates.toPlainText(), provenance=self.provenance.toPlainText(),
                    accept_host=self.accept_host.isChecked(), accept_redshift=self.accept_redshift.isChecked())

    def select(self, index):
        if self.index >= 0: self.drafts[self.index] = self.capture()
        self.index = index
        if index < 0: return
        record = self.document['spectra'][index]
        draft = self.drafts.get(index)
        for key, field in self.fields.items():
            value = draft['fields'][key] if draft else record.get(key)
            value = '' if value is None else str(value)
            if isinstance(field, Q.QComboBox): field.setCurrentText(value)
            else: field.setText(value)
        self.candidates.setPlainText(draft['candidates'] if draft else json.dumps(record['host_candidates'], indent=2))
        self.provenance.setPlainText(draft['provenance'] if draft else json.dumps(record['provenance'], indent=2))
        self.accept_host.setChecked(draft['accept_host'] if draft else False)
        self.accept_redshift.setChecked(draft['accept_redshift'] if draft else False)
        self.review_info.setText('Saved reviews: '+json.dumps({k:record[k] for k in ('host_review','redshift_review','review') if k in record}))

    def save(self):
        try:
            self.drafts[self.index] = self.capture()
            doc = deepcopy(self.document); hosts = []; redshifts = []
            for index, draft in self.drafts.items():
                record = doc['spectra'][index]
                for key, value in draft['fields'].items():
                    if key in NUMERIC: value = float(value) if value.strip() else None
                    if value in ('', None): record.pop(key, None)
                    else: record[key] = value
                record['host_candidates'] = json.loads(draft['candidates'])
                record['provenance'] = json.loads(draft['provenance'])
                if draft['accept_host']: hosts.append(record['path'])
                if draft['accept_redshift']: redshifts.append(record['path'])
            saved = metadata.save(self.run, doc, self.reviewer.text(), accept_hosts=hosts, accept_redshifts=redshifts,
                                  expected_revision=self.document.get('revision_id'))
            index = self.index; self.open_run(self.run); self.spectra.setCurrentIndex(index)
            self.notice.setText('Saved metadata revision '+saved['revision_id']+'. Refresh the nightly HTML to display it.')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.notice.setText('Metadata not saved: '+str(exc))

    def refresh_report(self):
        try:
            result = metadata.refresh_report(self.run)
            self.notice.setText('Refreshed saved metadata in '+str(result.get('path', self.run.parent.parent.parent/'index.html')))
        except (OSError, ValueError, KeyError) as exc:
            self.notice.setText('Report not refreshed: '+str(exc))
