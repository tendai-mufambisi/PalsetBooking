import os
import requests
import hmac
import hashlib
from django.conf import settings
import logging
import time

logger = logging.getLogger(__name__)


class PaynowService:
    """Paynow integration wrapper with optional use of the `paynow` SDK.

    Responsibilities:
      - create_transaction: create a payment and return necessary redirect/poll urls
      - verify_notification: verify webhook requests from Paynow using HMAC-SHA256 over the raw body

    NOTE: Paynow's exact signature scheme should be verified against their docs. This
    implementation uses an HMAC-SHA256 over the raw POST body with the integration key.
    If Paynow uses a different algorithm, update `verify_notification` accordingly.
    """

    CREATE_URL = "https://www.paynow.co.zw/interface/initiatetransaction"

    def __init__(self):
        self.integration_id = settings.PAYNOW_INTEGRATION_ID
        self.integration_key = settings.PAYNOW_INTEGRATION_KEY
        self.return_url = settings.PAYNOW_RETURN_URL
        self.result_url = settings.PAYNOW_RESULT_URL

    def create_transaction(self, amount: float, reference: str, email: str, phone: str, return_url: str = None) -> dict:
        logger.info('=== PAYNOW CREATE_TRANSACTION START ===')
        logger.info('amount=%s, reference=%s, email=%s, phone=%s', amount, reference, email, phone)

        if not self.integration_id or not self.integration_key:
            raise RuntimeError("Paynow integration credentials not set")

        # Try to use the paynow library if available
        # 
        try:
            from paynow import Paynow
            paynow = Paynow(self.integration_id,
                             self.integration_key,
                             self.return_url, 
                             self.result_url)

    

                # Use merchant authemail in test mode (Paynow requires the authemail to match
            # the merchant email for faked test payments). Fall back to the provided
            # customer email if no merchant email is configured.
            authemail = getattr(settings, 'PAYNOW_MERCHANT_EMAIL', None) or email
            payment = paynow.create_payment(reference, authemail)
            payment.add('Taxi booking', float(amount))
            logger.debug('Creating payment with authemail=%s reference=%s', authemail, payment.reference)
          
            # Use the generic send method so we DO NOT choose or force a specific payment method
            # on behalf of the user. The customer must pick the method on Paynow's hosted page.
            response = paynow.send(payment)
            logger.debug('SDK init response received')
            logger.info('=== SDK RESPONSE DETAILS ===')
            logger.info('Response object type: %s', type(response))
            logger.info('Response object attributes: %s', dir(response))

            # Try to access all common attributes on the response
            for attr in ['success', 'error', 'status', 'redirect_url', 'redirectUrl', 'poll_url', 'pollUrl', 'message', 'data', 'instruction']:
                try:
                    val = getattr(response, attr, 'ATTRIBUTE_NOT_FOUND')
                    logger.info('response.%s = %s (type: %s)', attr, val, type(val).__name__)
                except Exception as ex:
                    logger.exception('Error accessing response.%s: %s', attr, ex)

            # Diagnostic logging
            logger.debug('SDK InitResponse repr: %s', getattr(response, '__dict__', {}))
            for a in ("success", "error", "status", "redirect_url", "poll_url", "message"):
                logger.debug('%s = %s', a, getattr(response, a, None))

            # Convert SDK response to a JSON-serializable dict
            def _clean_value(v):
                if v is None or isinstance(v, (str, int, float, bool)):
                    return v
                # Don't stringify type objects
                if isinstance(v, type):
                    return None
                try:
                    if isinstance(v, dict):
                        return {str(k): _clean_value(val) for k, val in v.items()}
                    if isinstance(v, (list, tuple)):
                        return [_clean_value(x) for x in v]
                except Exception:
                    pass
                try:
                    return str(v)
                except Exception:
                    return repr(v)

            raw_data = getattr(response, 'data', None) or {}
            cleaned_data = _clean_value(raw_data)

            # Response provides redirect_url and poll_url
            link = getattr(response, 'redirect_url', None) or getattr(response, 'redirectUrl', None)
            pollUrl = getattr(response, 'poll_url', None) or getattr(response, 'pollUrl', None)

            # If the SDK indicates success, return the normal payload; otherwise fall back
            if getattr(response, 'success', True):
                resp_dict = {
                    'success': bool(getattr(response, 'success', True)),
                    'error': _clean_value(getattr(response, 'error', None)),
                    'status': _clean_value(getattr(response, 'status', None)),
                    'redirect_url': _clean_value(link),
                    'poll_url': _clean_value(pollUrl),
                    'instruction': _clean_value(getattr(response, 'instruction', None)),
                    'data': cleaned_data,
                }

                return {
                    'reference': reference,
                    'redirectUrl': _clean_value(link),
                    'pollUrl': _clean_value(pollUrl),
                    'response': resp_dict,
                }

            # Not a success, but the SDK may still provide useful information such as
            # a poll_url or paynow reference; include those so the caller can treat
            # the transaction as 'initiated / pending' instead of an outright failure.
            logger.warning('The response is not success; response: %s', repr(response))
            # Convert response.data to a JSON-serializable dict if present
            raw_data = getattr(response, 'data', None) or {}
            try:
                cleaned = _clean_value(raw_data)
            except Exception:
                cleaned = str(raw_data)

            # Try to discover a poll url or paynow reference in common fields
            pollUrl = getattr(response, 'poll_url', None) or getattr(response, 'pollUrl', None) or cleaned.get('poll_url') or cleaned.get('pollUrl')
            paynow_ref = cleaned.get('paynowreference') or cleaned.get('paynow_reference') or cleaned.get('paynowReference')

            resp_dict = {
                'success': bool(getattr(response, 'success', False)),
                'error': _clean_value(getattr(response, 'error', None)),
                'status': _clean_value(getattr(response, 'status', None)),
                'redirect_url': None,
                'poll_url': _clean_value(pollUrl),
                'instruction': _clean_value(getattr(response, 'instruction', None)),
                'data': cleaned,
            }

            out = {
                'reference': reference,
                'redirectUrl': None,
                'pollUrl': _clean_value(pollUrl),
                'response': resp_dict,
                'error': 'init_not_success',
            }
            if paynow_ref:
                out['paynowreference'] = _clean_value(paynow_ref)
                out['paynow_reference'] = _clean_value(paynow_ref)

            return out

            
        except Exception as e:
            # Fall back to HTTP implementation if SDK not available or fails
            logger.info('SDK flow not available, falling back to HTTP: %s', e)
            # For the HTTP fallback, ensure authemail is set to the merchant's email in test mode
            authemail = getattr(settings, 'PAYNOW_MERCHANT_EMAIL', None) or email
            payload = {
                "id": self.integration_id,
                "amount": f"{amount:.2f}",
                "reference": reference,
                "returnUrl": return_url or self.return_url,
                "resultUrl": self.result_url,
                "authemail": authemail,
                "phone": phone,
            }

            # Respect the PAYNOW_VERIFY_SSL setting (False can help local dev when OCSP/CRL
            # checks are failing, but DO NOT disable in production).
            verify_ssl = getattr(settings, 'PAYNOW_VERIFY_SSL', True)

            try:
                logger.info('Sending HTTP request to Paynow: %s', self.CREATE_URL)
                logger.info('Payload: %s', payload)
                resp = requests.post(self.CREATE_URL, data=payload, timeout=15, verify=verify_ssl)
                logger.info('Response status: %s', resp.status_code)
                logger.info('Response headers: %s', dict(resp.headers))
            except requests.exceptions.SSLError as e:
                logger.exception('SSL error when contacting Paynow init endpoint: %s', e)
                return {
                    'reference': reference,
                    'redirectUrl': None,
                    'raw_response': '',
                    'status_code': None,
                    'error': 'ssl_error',
                    'message': str(e),
                }
            except requests.exceptions.ConnectTimeout as e:
                logger.exception('Paynow connection timed out when posting init: %s', e)
                return {
                    'reference': reference,
                    'redirectUrl': None,
                    'raw_response': '',
                    'status_code': None,
                    'error': 'connect_timeout',
                    'message': str(e),
                }
            except requests.exceptions.ConnectionError as e:
                logger.exception('Paynow connection error when posting init: %s', e)
                return {
                    'reference': reference,
                    'redirectUrl': None,
                    'raw_response': '',
                    'status_code': None,
                    'error': 'connection_error',
                    'message': str(e),
                }
            except Exception as e:
                logger.exception('Unexpected error when contacting Paynow init endpoint: %s', e)
                return {
                    'reference': reference,
                    'redirectUrl': None,
                    'raw_response': '',
                    'status_code': None,
                    'error': 'request_exception',
                    'message': str(e),
                }

            # Handle HTTP error status codes explicitly and return structured errors
            try:
                resp.raise_for_status()
            except requests.HTTPError as e:
                body = getattr(resp, 'text', '')
                logger.exception('Paynow HTTP error status %s: %s', getattr(resp, 'status_code', None), (body or '')[:1000])
                return {
                    'reference': reference,
                    'redirectUrl': None,
                    'raw_response': body,
                    'status_code': getattr(resp, 'status_code', None),
                    'error': 'http_error',
                    'message': str(e),
                }

            # Attempt to parse JSON, but handle non-JSON responses gracefully
            try:
                # If the response body is empty but status is 200, treat as a benign empty response
                text = (resp.text or '').strip()
                logger.info('Response text length: %s, first 500 chars: %s', len(text), text[:500])
                if resp.status_code == 200 and text == '':
                    logger.info('Paynow returned empty 200 response; returning safe fallback. Headers: %s', resp.headers)
                    return {
                        'reference': reference,
                        'redirectUrl': None,
                        'raw_response': '',
                        'status_code': resp.status_code,
                    }

                # Try to parse JSON; requests may raise a RequestsJSONDecodeError which
                # isn't always caught by ValueError handlers in some environments, so
                # catch it explicitly and fall back to returning the raw response.
                try:
                    json_response = resp.json()
                    logger.info('Successfully parsed JSON response: %s', json_response)
                    # Wrap the raw Paynow JSON response in our expected structure
                    wrapped_response = {
                        'reference': reference,
                        'redirectUrl': json_response.get('redirectUrl') or json_response.get('redirect_url'),
                        'pollUrl': json_response.get('pollUrl') or json_response.get('poll_url'),
                        'paynowreference': json_response.get('paynowreference') or json_response.get('paynow_reference'),
                        'paynow_reference': json_response.get('paynowreference') or json_response.get('paynow_reference'),
                        'response': json_response,
                    }
                    logger.info('Wrapped response: %s', wrapped_response)
                    return wrapped_response
                except Exception as json_exc:
                    logger.exception('Paynow returned non-JSON response; returning raw HTML. Exception: %s', json_exc)
                    # Limit logged output size for safety
                    sample = (resp.text or '')[:8000]
                    logger.debug('Paynow raw response (truncated): %s', sample)
                    return {
                        'reference': reference,
                        'redirectUrl': None,
                        'raw_response': resp.text,
                        'status_code': resp.status_code,
                    }
            except Exception as e:
                logger.exception('Unexpected error handling Paynow response: %s', e)
                return {
                    'reference': reference,
                    'redirectUrl': None,
                    'raw_response': getattr(resp, 'text', '') if 'resp' in locals() else '',
                    'status_code': getattr(resp, 'status_code', None) if 'resp' in locals() else None,
                }


    def verify_notification(self, request) -> bool:
        logger.debug('Entering verify_notification')
        logger.debug('Paynow headers: %s', {k:v for k,v in request.META.items() if k.startswith('HTTP_')})
        logger.debug('Content-Type: %s', request.META.get('CONTENT_TYPE'))
        logger.debug('Raw body (bytes): %s', request.body[:2000])
        """Verify an incoming Paynow webhook notification.

        Current verification logic:
        - Looks for header 'X-Paynow-Signature' and compares it to HMAC-SHA256 of the raw body
        - Falls back to a POST parameter 'signature' if header is missing

        Returns True if signature verifies, False otherwise.
        """
        key = (self.integration_key or '').encode()
        if not key:
            logger.warning("No Paynow integration key configured; cannot verify signature")
            return False

        raw = request.body or b''

        expected = hmac.new(key, raw, hashlib.sha256).hexdigest()

        header_sig = request.META.get('HTTP_X_PAYNOW_SIGNATURE')
        if header_sig:
            logger.debug('Found header signature')
            return hmac.compare_digest(expected, header_sig)

        post_sig = request.POST.get('signature')
        if post_sig:
            logger.debug('Found post signature')
            return hmac.compare_digest(expected, post_sig)

        # Some Paynow integrations send a parameter named `hash` instead of a signature header.
        # Attempt to verify against a few likely schemes (HMAC-SHA256, HMAC-SHA512, SHA256(key+body), SHA512(key+body)).
        post_hash = request.POST.get('hash')
        if post_hash:
            logger.debug('Found post hash: %s', post_hash[:64])
            # normalize
            incoming = post_hash.strip().lower()
            # compute possibilities
            try:
                h256 = hmac.new(key, raw, hashlib.sha256).hexdigest()
                h512 = hmac.new(key, raw, hashlib.sha512).hexdigest()
                s256 = hashlib.sha256(raw + key).hexdigest()
                s512 = hashlib.sha512(raw + key).hexdigest()
            except Exception as e:
                logger.exception('Error computing fallback hashes: %s', e)
                return False

            for candidate in (h256, h512, s256, s512):
                if candidate and hmac.compare_digest(candidate.lower(), incoming):
                    logger.debug('Post hash verified using candidate %s', 'h256' if candidate==h256 else 'other')
                    return True

            # Extended diagnostics (only in DEBUG) - try common Paynow schemes and field-order concatenations
            if settings.DEBUG:
                logger.debug('Running extended Paynow hash diagnostics')
                try:
                    from urllib.parse import unquote_plus
                    # Try raw body without the hash param
                    raw_no_hash = raw
                    try:
                        idx = raw.lower().find(b'&hash=')
                        if idx != -1:
                            raw_no_hash = raw[:idx]
                    except Exception:
                        pass

                    candidates = {}

                    # HMAC-SHA512 over raw_no_hash
                    candidates['hmac_sha512_raw_no_hash'] = hmac.new(key, raw_no_hash, hashlib.sha512).hexdigest()
                    # HMAC-SHA512 over url-decoded raw_no_hash
                    try:
                        decoded = unquote_plus(raw_no_hash.decode('utf-8'))
                        candidates['hmac_sha512_decoded'] = hmac.new(key, decoded.encode('utf-8'), hashlib.sha512).hexdigest()
                    except Exception:
                        candidates['hmac_sha512_decoded'] = None

                    # Raw concatenation of individual fields in common order
                    post = request.POST
                    ref = post.get('reference', '')
                    payref = post.get('paynowreference', '')
                    amount = post.get('amount', '')
                    status_v = post.get('status', '')
                    pollurl = post.get('pollurl', '')

                    concat = f"{ref}{payref}{amount}{status_v}{pollurl}{self.integration_key}"
                    candidates['sha512_concat_values_end_key'] = hashlib.sha512(concat.encode('utf-8')).hexdigest()

                    concat2 = f"{self.integration_key}{ref}{payref}{amount}{status_v}{pollurl}"
                    candidates['sha512_concat_key_start'] = hashlib.sha512(concat2.encode('utf-8')).hexdigest()

                    # Try lowercased status
                    concat_low = f"{ref}{payref}{amount}{status_v.lower()}{pollurl}{self.integration_key}"
                    candidates['sha512_concat_values_status_lower'] = hashlib.sha512(concat_low.encode('utf-8')).hexdigest()

                    # HMAC-SHA512 over concatenated values
                    candidates['hmac_sha512_concat_values'] = hmac.new(key, f"{ref}{payref}{amount}{status_v}{pollurl}".encode('utf-8'), hashlib.sha512).hexdigest()

                    # Log and check candidates
                    for name, cand in candidates.items():
                        if cand is None:
                            continue
                        logger.debug('%s = %s', name, cand[:64])
                        if hmac.compare_digest(cand.lower(), incoming):
                            logger.info('Paynow hash verified using %s', name)
                            return True

                except Exception as e:
                    logger.exception('Error during extended Paynow diagnostics: %s', e)

            logger.warning('Post hash did not match any computed candidate')
            return False

        logger.warning("No signature provided in Paynow notification")
        return False

    def verify_payment(self, poll_url: str) -> dict:
        """Check transaction status using SDK if available or HTTP poll"""
        try:
            from paynow import Paynow
            paynow = Paynow(self.integration_id, self.integration_key, self.return_url, self.result_url)
            status = paynow.check_transaction_status(poll_url)
            
            # Log all attributes of the status object to debug
            logger.info('=== VERIFY_PAYMENT: SDK Status Object ===')
            logger.info(f'Status object type: {type(status)}')
            logger.info(f'Status object: {status}')
            logger.info(f'Status repr: {repr(status)}')
            logger.info(f'Status dir: {[attr for attr in dir(status) if not attr.startswith("_")]}')
            
            # Try multiple common attribute names
            paid_via_paid = getattr(status, 'paid', None)
            paid_via_success = getattr(status, 'success', None)
            paid_via_payment_received = getattr(status, 'payment_received', None)
            paid_via_data = None
            
            # Check if status has a 'data' attribute that might contain payment info
            data_attr = getattr(status, 'data', None)
            if data_attr:
                paid_via_data = data_attr.get('paid') if isinstance(data_attr, dict) else getattr(data_attr, 'paid', None)
            
            logger.info(f'paid attribute: {paid_via_paid}')
            logger.info(f'success attribute: {paid_via_success}')
            logger.info(f'payment_received attribute: {paid_via_payment_received}')
            logger.info(f'data.paid: {paid_via_data}')
            
            status_str = getattr(status, 'status', None)
            logger.info(f'status attribute: {status_str}')
            
            # Determine if paid based on available attributes
            is_paid = False
            if paid_via_paid is True:
                is_paid = True
            elif paid_via_success is True:
                is_paid = True
            elif paid_via_payment_received is True:
                is_paid = True
            elif paid_via_data is True:
                is_paid = True
            elif status_str and isinstance(status_str, str):
                # Check status string for payment indicators
                status_lower = status_str.lower()
                if any(x in status_lower for x in ('paid', 'success', 'ok', 'completed')):
                    is_paid = True
            
            logger.info(f'Final decision: paid={is_paid}')
            return {'paid': is_paid, 'status': status_str}
        except Exception:
            # Fallback to an HTTP probe that attempts to handle common Paynow responses.
            # This is more tolerant for environments without the Paynow SDK.
            try:
                verify_ssl = getattr(settings, 'PAYNOW_VERIFY_SSL', True)
                resp = requests.get(poll_url, timeout=10, verify=verify_ssl, allow_redirects=True)
            except Exception as e:
                logger.exception('HTTP poll to Paynow failed: %s', e)
                # Give up gracefully: return pending with error status
                return {'paid': False, 'status': f'poll_error: {e}'}

            text = (resp.text or '')
            # Try parse JSON first
            try:
                data = resp.json()
            except Exception:
                data = None

            # Inspect JSON response for common fields
            if isinstance(data, dict):
                # Known keys that may indicate payment
                paid = False
                status_val = None
                # boolean 'paid'
                if 'paid' in data and isinstance(data.get('paid'), bool):
                    paid = data.get('paid')
                    status_val = str(data.get('status') or data.get('message') or data.get('result') or status_val)
                    return {'paid': bool(paid), 'status': status_val or 'paid' if paid else 'pending'}

                # textual status fields
                for k in ('status', 'payment_status', 'result', 'message'):
                    if k in data and data[k] is not None:
                        try:
                            s = str(data[k])
                        except Exception:
                            s = None
                        if s:
                            low = s.lower()
                            if any(x in low for x in ('paid', 'success', 'completed')):
                                return {'paid': True, 'status': s}
                            if any(x in low for x in ('pending', 'awaiting', 'awaiting delivery', 'awaiting payment')):
                                return {'paid': False, 'status': s}
                            status_val = s
                # Fallback: return unknown textual status
                return {'paid': False, 'status': status_val or 'unknown'}

            # No JSON — inspect HTML/text for keywords
            low = text.lower()
            if any(k in low for k in ('paid', 'payment received', 'payment successful', 'success')):
                return {'paid': True, 'status': 'Paid (scraped)'}
            if any(k in low for k in ('awaiting delivery', 'awaiting payment', 'pending', 'not paid')):
                return {'paid': False, 'status': 'Pending (scraped)'}

            # If nothing matched, return pending with a snippet for diagnostics
            snippet = (text or '')[:1000]
            logger.debug('Paynow poll HTTP response snippet: %s', snippet[:800])
            return {'paid': False, 'status': 'Unknown (scraped)'}
