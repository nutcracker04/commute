/**
 * Commute — Google Form → POST /api/drivers (multipart)
 *
 * Paste into the Form-bound Apps Script project (Extensions → Apps Script).
 * Set Script property: WORKER_BASE (worker origin, no trailing slash).
 */

var CONFIG = {
  FIELD_NAME: 'Name',
  FIELD_PHONE: 'Number',
  FIELD_REF_ID: 'Reference Id',
  FIELD_UPI: 'UPI QR',
  FIELD_IDENTITY: 'Identity Proof',
  ERRORS_SHEET_NAME: 'Form sync errors',
};

/**
 * Installable trigger: Form → On form submit → this function.
 */
function onFormSubmit(e) {
  if (!e || !e.namedValues) {
    Logger.log(
      'Commute: onFormSubmit needs a real form-submit event. Add an installable trigger: Form → On form submit → onFormSubmit (do not Run from the editor with no argument).'
    );
    return;
  }

  var props = PropertiesService.getScriptProperties();
  var base = (props.getProperty('WORKER_BASE') || '').replace(/\/$/, '');

  if (!base) {
    Logger.log('Commute: set WORKER_BASE in Project Settings → Script properties');
    return;
  }

  try {
    var nv = e.namedValues;
    var name = firstAnswer_(nv, CONFIG.FIELD_NAME);
    var phone = firstAnswer_(nv, CONFIG.FIELD_PHONE);
    var refId = firstAnswer_(nv, CONFIG.FIELD_REF_ID);
    var upiUrl = firstAnswer_(nv, CONFIG.FIELD_UPI);
    var idUrl = firstAnswer_(nv, CONFIG.FIELD_IDENTITY);

    if (!name || !phone || !refId) {
      try {
        Logger.log(
          'Commute: expected question titles exactly: "' +
            CONFIG.FIELD_NAME +
            '", "' +
            CONFIG.FIELD_PHONE +
            '", "' +
            CONFIG.FIELD_REF_ID +
            '". This submission has titles: ' +
            JSON.stringify(Object.keys(nv).sort())
        );
      } catch (kvErr) {
        /* ignore */
      }
      logError_(e, 0, 'Missing Name, Phone, or Reference Id', name, phone, refId);
      return;
    }

    var upiFileId = extractDriveFileId_(upiUrl);
    var identityFileId = extractDriveFileId_(idUrl);
    if (!upiFileId || !identityFileId) {
      logError_(
        e,
        0,
        'Could not parse Drive file id from UPI or Identity field (expected a Drive URL)',
        name,
        phone,
        refId
      );
      return;
    }

    var upiBlob = DriveApp.getFileById(upiFileId).getBlob();
    var idBlob = DriveApp.getFileById(identityFileId).getBlob();

    var boundary = '----CommuteBoundary' + Utilities.getUuid().replace(/-/g, '');
    var bodyBytes = buildMultipartDriverCreate_(boundary, name, phone, refId, upiBlob, idBlob);

    var url = base + '/api/drivers';
    var resp = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'multipart/form-data; boundary=' + boundary,
      payload: bodyBytes,
      muteHttpExceptions: true,
    });

    var code = resp.getResponseCode();
    var text = resp.getContentText();
    if (code < 200 || code >= 300) {
      logError_(e, code, text, name, phone, refId);
    }
  } catch (err) {
    var msg = String(err.message || err);
    if (e && e.source) {
      logError_(e, 0, msg, '', '', '');
    } else {
      Logger.log('Commute onFormSubmit error (no form context for sheet log): ' + msg);
    }
  }
}

function firstAnswer_(namedValues, title) {
  var arr = namedValues[title];
  if (!arr || !arr.length) return '';
  return String(arr[0] || '').trim();
}

/**
 * Google Form file-upload answers are usually a hyperlink or URL to Drive.
 */
function extractDriveFileId_(text) {
  if (!text) return '';
  var s = String(text).trim();
  var m = s.match(/\/file\/d\/([a-zA-Z0-9_-]+)/);
  if (m) return m[1];
  m = s.match(/[?&]id=([a-zA-Z0-9_-]+)/);
  if (m) return m[1];
  if (/^[a-zA-Z0-9_-]{25,}$/.test(s)) return s;
  return '';
}

function utf8Bytes_(str) {
  return Utilities.newBlob(str != null ? String(str) : '').getBytes();
}

function crlfBytes_() {
  return utf8Bytes_('\r\n');
}

function concatBytes_(arrays) {
  var total = 0;
  var i;
  for (i = 0; i < arrays.length; i++) {
    total += arrays[i].length;
  }
  var out = [];
  out.length = total;
  var pos = 0;
  for (i = 0; i < arrays.length; i++) {
    var a = arrays[i];
    for (var j = 0; j < a.length; j++) {
      out[pos++] = a[j];
    }
  }
  return out;
}

function escapeFilename_(name) {
  return String(name || 'upload.bin').replace(/"/g, '_').replace(/\r|\n/g, '_');
}

function addTextPart_(chunks, boundary, fieldName, value) {
  chunks.push(utf8Bytes_('--' + boundary + '\r\n'));
  chunks.push(
    utf8Bytes_('Content-Disposition: form-data; name="' + fieldName + '"\r\n\r\n')
  );
  chunks.push(utf8Bytes_(String(value)));
  chunks.push(crlfBytes_());
}

function addFilePart_(chunks, boundary, fieldName, blob) {
  var fname = escapeFilename_(blob.getName());
  var ct = blob.getContentType() || 'application/octet-stream';
  chunks.push(utf8Bytes_('--' + boundary + '\r\n'));
  chunks.push(
    utf8Bytes_(
      'Content-Disposition: form-data; name="' +
        fieldName +
        '"; filename="' +
        fname +
        '"\r\n'
    )
  );
  chunks.push(utf8Bytes_('Content-Type: ' + ct + '\r\n\r\n'));
  chunks.push(blob.getBytes());
  chunks.push(crlfBytes_());
}

function buildMultipartDriverCreate_(boundary, name, phone, refId, upiBlob, idBlob) {
  var chunks = [];
  addTextPart_(chunks, boundary, 'name', name);
  addTextPart_(chunks, boundary, 'phone', phone);
  addTextPart_(chunks, boundary, 'qr_ref_id', refId);
  addFilePart_(chunks, boundary, 'upi_qr', upiBlob);
  addFilePart_(chunks, boundary, 'identity', idBlob);
  chunks.push(utf8Bytes_('--' + boundary + '--\r\n'));
  return concatBytes_(chunks);
}

function respondentEmail_(e) {
  try {
    if (e.response && e.response.getRespondentEmail) {
      return e.response.getRespondentEmail() || '';
    }
  } catch (x) {
    /* ignore */
  }
  return '';
}

/**
 * Appends a row to the linked response spreadsheet tab CONFIG.ERRORS_SHEET_NAME.
 * Requires the Form to be linked to a spreadsheet (Select response destination).
 */
function logError_(e, httpCode, responseBody, name, phone, refId) {
  var snippet = String(responseBody || '');
  if (snippet.length > 2000) snippet = snippet.substring(0, 2000);

  try {
    if (!e || !e.source) {
      Logger.log(
        'Commute error (no form event): HTTP ' +
          httpCode +
          ' ' +
          snippet +
          ' | name=' +
          name +
          ' phone=' +
          phone +
          ' refId=' +
          refId
      );
      return;
    }
    var form = e.source;
    var destId = form.getDestinationId && form.getDestinationId();
    if (!destId) {
      Logger.log(
        'Commute: ' +
          snippet +
          ' (HTTP ' +
          httpCode +
          '). name="' +
          name +
          '" phone="' +
          phone +
          '" refId="' +
          refId +
          '". No response spreadsheet is linked, so this was not written to a sheet — Form → Responses → Link to Sheets to enable the "Form sync errors" tab.'
      );
      return;
    }

    var ss = SpreadsheetApp.openById(destId);
    var sh = ss.getSheetByName(CONFIG.ERRORS_SHEET_NAME);
    if (!sh) {
      sh = ss.insertSheet(CONFIG.ERRORS_SHEET_NAME);
      sh.appendRow([
        'Timestamp',
        'HTTP',
        'Response',
        'Name',
        'Phone',
        'RefId',
        'RespondentEmail',
      ]);
    }
    sh.appendRow([
      new Date(),
      httpCode,
      snippet,
      name,
      phone,
      refId,
      respondentEmail_(e),
    ]);
  } catch (err2) {
    Logger.log('Commute logError_ failed: ' + err2 + ' | original: ' + snippet);
  }
}
