/**
 * Commute — Google Form → POST /api/drivers (multipart)
 *
 * Script property: WORKER_BASE (worker origin, no trailing slash).
 *
 * Installable trigger “On form submit” exists in two flavors — pick ONE:
 *   • Event source: From spreadsheet → use the script project bound to the response Sheet.
 *   • Event source: From form → use the script project bound to the Form.
 * The event payload differs: spreadsheet gives e.namedValues; form gives e.response (no namedValues).
 * This file handles both. Re-authorize the script after changing triggers if Google prompts you.
 *
 * A new row added manually / imported does NOT fire form submit — only real Form submissions do.
 * Testing: submit via the Form preview link. Editor ▶ Run passes no payload.
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
 * Installable “On form submit” only — see file header. Editor ▶ Run has no payload.
 */
function onFormSubmit(e) {
  if (!e) {
    Logger.log(
      'Commute: missing event (did you click Run in the editor?). Submit the Form to test.'
    );
    return;
  }

  var nv = e.namedValues;
  if (!nv && e.response) {
    nv = namedValuesFromFormResponse_(e.response);
    if (nv && Object.keys(nv).length) {
      Logger.log('Commute: using Form-bound trigger (built namedValues from e.response).');
    }
  }
  if (!nv || !Object.keys(nv).length) {
    Logger.log(
      'Commute: no answers found. Use installable trigger On form submit (From spreadsheet OR From form), ' +
        'then submit the Form — not only add a sheet row. Raw keys on e: ' +
        JSON.stringify(Object.keys(e).sort())
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
    // UrlFetchApp only treats string/Blob as raw body; a plain array is coerced wrongly and breaks multipart.
    var payloadBlob = Utilities.newBlob(bodyBytes);

    var url = base + '/api/drivers';
    var resp = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'multipart/form-data; boundary=' + boundary,
      payload: payloadBlob,
      muteHttpExceptions: true,
    });

    var code = resp.getResponseCode();
    var text = resp.getContentText();
    if (code < 200 || code >= 300) {
      logError_(e, code, text, name, phone, refId);
    } else {
      Logger.log('Commute: driver created OK (HTTP ' + code + ') ' + text);
    }
  } catch (err) {
    var msg = String(err.message || err);
    if (getResponseSpreadsheetId_(e)) {
      logError_(e, 0, msg, '', '', '');
    } else {
      Logger.log('Commute onFormSubmit error (no spreadsheet context for sheet log): ' + msg);
    }
  }
}

/**
 * Form-bound “On form submit” trigger populates e.response, not e.namedValues.
 * Builds the same shape as spreadsheet-bound triggers: { "Question title": ["answer"] }.
 */
function namedValuesFromFormResponse_(response) {
  var nv = {};
  if (!response || !response.getItemResponses) return nv;
  var items = response.getItemResponses();
  var i;
  for (i = 0; i < items.length; i++) {
    var ir = items[i];
    try {
      var item = ir.getItem();
      var title = item.getTitle && item.getTitle();
      if (!title) continue;
      var ans = ir.getResponse();
      if (ans === null || ans === undefined || ans === '') continue;
      if (Object.prototype.toString.call(ans) === '[object Array]') {
        nv[title] = ans;
      } else {
        nv[title] = [String(ans)];
      }
    } catch (rowErr) {
      /* skip bad item */
    }
  }
  return nv;
}

/** Spreadsheet-bound submit: e.source is Spreadsheet. Form-bound: e.source is Form with getDestinationId. */
function getResponseSpreadsheetId_(e) {
  if (!e || !e.source) return '';
  try {
    var s = e.source;
    if (s.getDestinationId) {
      var d = s.getDestinationId();
      if (d) return String(d);
    }
  } catch (x) {
    /* ignore */
  }
  try {
    if (e.source.getId) return String(e.source.getId());
  } catch (x2) {
    /* ignore */
  }
  return '';
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
  // /file/d/ID or /file/u/<account>/d/ID (multi-login Drive URLs)
  var m = s.match(/\/file\/(?:u\/\d+\/)?d\/([a-zA-Z0-9_-]+)/);
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
    var destId = getResponseSpreadsheetId_(e);
    if (!destId) {
      Logger.log(
        'Commute error (no spreadsheet id): HTTP ' +
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
