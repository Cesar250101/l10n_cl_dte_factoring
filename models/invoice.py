# -*- coding: utf-8 -*-
from openerp import fields, models, api, _
from openerp.exceptions import UserError
from datetime import datetime, timedelta, date
import logging
from lxml import etree
from lxml.etree import Element, SubElement
from openerp import SUPERUSER_ID

import pytz
import collections

_logger = logging.getLogger(__name__)

try:
    import xmltodict
except ImportError:
    _logger.info('Cannot import xmltodict library')

try:
    import dicttoxml
except ImportError:
    _logger.info('Cannot import dicttoxml library')

try:
    import base64
except ImportError:
    _logger.info('Cannot import base64 library')

class CesionDTE(models.Model):
    _inherit = "account.invoice"

    cesion_number = fields.Integer(
        copy=False,
        string='Cesion Number',
        help='',
    )
    declaracion_jurada = fields.Text(
        copy=False,
        string='Declaración Jurada',
        help='',
    )
    cesionario_id = fields.Many2one(
        'res.partner',
        string="Cesionario",
        help='',
    )
    sii_cesion_result = fields.Selection([
        ('', 'n/a'),
        ('NoEnviado', 'No Enviado'),
        ('EnCola','En cola de envío'),
        ('Enviado', 'Enviado'),
        ('Aceptado', 'Aceptado'),
        ('Rechazado', 'Rechazado'),
        ('Reparo', 'Reparo'),
        ('Proceso', 'Procesado'),
        ('Reenviar', 'Reenviar'),
        ('Anulado', 'Anulado')],
        string='Resultado Cesion',
        copy=False,
        help="SII request result",
    )
    imagen_ar_ids = fields.One2many(
        'account.invoice.imagen_ar',
        'invoice_id',
        string="Imagenes de acuse de recibo",
    )

    def _get_xsd_types(self):
        xsd_types = super(InvoiceDTE, self)._get_xsd_types()
        xsd_types.update({
            'aec': 'AEC_v10.xsd',
            'dte_ced': 'DTECedido_v10.xsd',
            'ces': 'Cesion_v10.xsd',
        })
        return xsd_types

    def _caratula_aec(self, cesiones):
        xml = '''<DocumentoAEC ID="SetDoc">
    <Caratula version="1.0">
    <RutCedente>{0}</RutCedente>
    <RutCesionario>{1}</RutCesionario>
    <NmbContacto>{2}</NmbContacto>
    <FonoContacto>{3}</FonoContacto>
    <MailContacto>{4}</MailContacto>
    <TmstFirmaEnvio>{5}</TmstFirmaEnvio>
</Caratula>
    <Cesiones>
        {6}
    </Cesiones>
</DocumentoAEC>
'''.format(
            self.format_vat(self.company_id.vat),
            self.format_vat(self.cesionario_id.commercial_partner_id.vat),
            self.responsable_envio.name,
            self.responsable_envio.phone or self.company_id.phone,
            self.responsable_envio.email or self.company_id.email,
            self.time_stamp(),
            cesiones,
        )
        return xml

    def crear_doc_cedido(self, doc):
        xml = '''<DTECedido xmlns="http://www.sii.cl/SiiDte" version="1.0">
{}
</DTECedido>'''.format(doc)
        return xml

    def _crear_info_trans_elec_aec(self, doc):
        xml = '''<Cesion xmlns="http://www.sii.cl/SiiDte" version="1.0">
{}
</Cesion>
'''.format(doc)

    def _crear_envio_aec(self, doc):
        xml = '''<?xml version="1.0" encoding="ISO-8859-1"?>
<AEC xmlns="http://www.sii.cl/SiiDte" \
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" \
xsi:schemaLocation="http://www.sii.cl/SiiDte Cesion_v10.xsd" \
version="1.0">
    {}
</AEC>'''.format(doc)
        return xml

    def _append_sig(self, type, msg, message):
        if type in ['aec']:
            fulldoc = self.create_template_doc1(message, msg)
            return fulldoc
        return super(InvoiceDTE, self)._append_sig(type, msg, message)

    @api.multi
    def get_cesion_xml_file(self):
        filename = (self.document_number+'.xml').replace(' ','')
        url_path = '/web/binary/download_document?model=account.invoice\
&field=sii_xml_request&id=%s&filename=%s' % (self.id, filename)
        return {
            'type' : 'ir.actions.act_url',
            'url': url_path,
            'target': 'self',
        }

    def _id_dte(self):
        IdDoc = collections.OrderedDict()
        IdDoc['TipoDTE'] = self.sii_document_class_id.sii_code
        IdDoc['RUTEmisor'] = self.format_vat(self.company_id.vat)
        if not self.partner_id.commercial_partner_id.vat and not self._es_boleta():
            raise UserError("Debe Ingresar RUT Receptor")
        IdDoc['RUTReceptor'] = self.format_vat(self.partner_id.commercial_partner_id.vat)
        IdDoc['Folio'] = self.get_folio()
        IdDoc['FchEmis'] = self.date_invoice
        IdDoc['MntTotal'] = self.amount_total
        return IdDoc

    def _cedente(self):
        Emisor = collections.OrderedDict()
        Emisor['RUT'] = self.format_vat(self.company_id.vat)
        Emisor['RazonSocial'] = self.company_id.partner_id.name
        Emisor['Direccion'] = self._acortar_str(self.company_id.street + ' ' +(self.company_id.street2 or ''), 70)
        Emisor['eMail'] = self.company_id.email or ''
        Emisor['RUTAutorizado'] = self.company_id.city or ''
        Emisor['DeclaracionJurada'] = self.declaracion_jurada
        return Emisor

    def _cesionario(self):
        Receptor = collections.OrderedDict()
        if not self.cesionario_id.commercial_partner_id.vat:
            raise UserError("Debe Ingresar RUT Receptor")
        Receptor['RUT'] = self.format_vat(self.cesionario_id.commercial_partner_id.vat)
        Receptor['RazonSocial'] = self._acortar_str(self.cesionario_id.commercial_partner_id.name, 100)
        Receptor['Direccion'] = self._acortar_str((self.cesionario_id.street or self.cesionario_id.commercial_partner_id.street) + ' ' + (self.cesionario_id.street2 or self.cesionario_id.commercial_partner_id.street2 or ''),70)
        Receptor['eMail'] = self.cesionario_id.commercial_partner_id.email
        return Receptor

    def _totales(self, MntExe=0, no_product=False, taxInclude=False):
        Totales = collections.OrderedDict()
        if self.sii_document_class_id.sii_code == 34 or (self.referencias and self.referencias[0].sii_referencia_TpoDocRef.sii_code == '34'):
            Totales['MntExe'] = int(round(self.amount_total, 0))
            if  no_product:
                Totales['MntExe'] = 0
        elif self.amount_untaxed and self.amount_untaxed != 0:
            if not self._es_boleta() or not taxInclude:
                IVA = False
                for t in self.tax_line_ids:
                    if t.tax_id.sii_code in [14, 15]:
                        IVA = t
                if IVA and IVA.base > 0 :
                    Totales['MntNeto'] = int(round((IVA.base), 0))
            if MntExe > 0:
                Totales['MntExe'] = int(round( MntExe))
            if not self._es_boleta() or not taxInclude:
                if IVA:
                    if not self._es_boleta():
                        Totales['TasaIVA'] = round(IVA.tax_id.amount,2)
                    Totales['IVA'] = int(round(IVA.amount, 0))
                if no_product:
                    Totales['MntNeto'] = 0
                    if not self._es_boleta():
                        Totales['TasaIVA'] = 0
                    Totales['IVA'] = 0
            if IVA and IVA.tax_id.sii_code in [15]:
                Totales['ImptoReten'] = collections.OrderedDict()
                Totales['ImptoReten']['TpoImp'] = IVA.tax_id.sii_code
                Totales['ImptoReten']['TasaImp'] = round(IVA.tax_id.amount,2)
                Totales['ImptoReten']['MontoImp'] = int(round(IVA.amount))
        monto_total = int(round(self.amount_total, 0))
        if no_product:
            monto_total = 0
        Totales['MntTotal'] = monto_total
        return Totales

    def _cesion_dte(self, n_atencion=None):
        dte = collections.OrderedDict()

        return dte

    def _dte_to_xml(self, dte, tpo_dte="Documento"):
        ted = dte[tpo_dte + ' ID']['TEDd']
        dte[(tpo_dte + ' ID')]['TEDd'] = ''
        xml = dicttoxml.dicttoxml(
            dte, root=False, attr_type=False) \
            .replace('<item>','').replace('</item>','')\
            .replace('<reflines>','').replace('</reflines>','')\
            .replace('<TEDd>','').replace('</TEDd>','')\
            .replace('</'+ tpo_dte + '_ID>','\n'+ted+'\n</'+ tpo_dte + '_ID>')
        return xml

    def _tpo_dte(self):
        tpo_dte = "Documento"
        if self.sii_document_class_id.sii_code == 43:
        	tpo_dte = 'Liquidacion'
        return tpo_dte

    def _crear_envio(self, n_atencion=None, RUTRecep="60803000-K"):
        dicttoxml.set_debug(False)
        cesiones = collections.OrderedDict()
        try:
            signature_d = self.get_digital_signature(inv.company_id)
        except:
            raise UserError(_('''There is no Signer Person with an \
        authorized signature for you in the system. Please make sure that \
        'user_signature_key' module has been installed and enable a digital \
        signature, for you or make the signer to authorize you to use his \
        signature.'''))
        certp = signature_d['cert'].replace(
            BC, '').replace(EC, '').replace('\n', '')
        file_name = ""
        file_name += ".xml"
        cesiones['DTECedido'] = self._cesion_dte()
        cesions['Cesion'] = self._crear_info_trans_elec_aec()
        env = 'aec'
        cartulado  = self._caratula_aec(
            cesiones,
        )
        envio_csion_dte = self._crear_envio_aec(caratulado)
        envio_dte = self.sign_full_xml(
            envio_dte,
            signature_d['priv_key'],
            certp,
            'SetDoc',
            env,
        )
        return envio_dte, file_name, company_id

    @api.multi
    def validate_cesion(self):
        for inv in self.with_context(lang='es_CL'):
            inv.sii_result = 'NoEnviado'
            inv.responsable_envio = self.env.user.id
            if inv.type in ['out_invoice', 'out_refund']:
                if inv.journal_id.restore_mode:
                    inv.sii_result = 'Proceso'
                else:
                    inv._timbrar()
                    self.env['sii.cola_envio'].create({
                                                'doc_ids':[inv.id],
                                                'model':'account.invoice',
                                                'user_id':self.env.user.id,
                                                'tipo_trabajo': 'pasivo',
                                                'date_time': (datetime.now() + timedelta(hours=12)),
                                                })
        super(invoice,self).invoice_validate()

    @api.multi
    def do_cesion_dte_send(self):
        ids = []
        for inv in self.with_context(lang='es_CL'):
            if inv.sii_result in ['','NoEnviado','Rechazado']:
                if inv.sii_result in ['Rechazado']:
                    inv._timbrar()
                inv.sii_result = 'EnCola'
                ids.append(inv.id)
        if ids:
            self.env['sii.cola_envio'].create({
                                    'doc_ids': ids,
                                    'model':'account.invoice',
                                    'user_id': self.env.user.id,
                                    'tipo_trabajo': 'envio',
                                    })

    @api.multi
    def do_dte_send(self, n_atencion=None):
        envio_dte, file_name, company_id = self._crear_envio(n_atencion, RUTRecep="60803000-K")
        result = self.send_xml_file(envio_dte, file_name, company_id)
        for inv in self:
            inv.write({'sii_xml_response':result['sii_xml_response'],
                'sii_send_ident':result['sii_send_ident'],
                'sii_result': result['sii_result'],
                'sii_xml_request':envio_dte,
                'sii_send_file_name' : file_name,
                })

    def _get_send_status(self, track_id, signature_d,token):
        url = server_url[self.company_id.dte_service_provider] + 'QueryEstUp.jws?WSDL'
        ns = 'urn:'+ server_url[self.company_id.dte_service_provider] + 'QueryEstUp.jws'
        _server = SOAPProxy(url, ns)
        rut = self.format_vat(self.company_id.vat, con_cero=True)
        respuesta = _server.getEstUp(
            rut[:8],
            str(rut[-1]),
            track_id,
            token)
        self.sii_receipt = respuesta
        resp = xmltodict.parse(respuesta)
        status = False
        if resp['SII:RESPUESTA']['SII:RESP_HDR']['ESTADO'] == "-11":
            if resp['SII:RESPUESTA']['SII:RESP_HDR']['ERR_CODE'] == "2":
                status =  {'warning':{'title':_('Estado -11'), 'message': _("Estado -11: Espere a que sea aceptado por el SII, intente en 5s más")}}
            else:
                status =  {'warning':{'title':_('Estado -11'), 'message': _("Estado -11: error 1Algo a salido mal, revisar carátula")}}
        if resp['SII:RESPUESTA']['SII:RESP_HDR']['ESTADO'] == "EPR":
            self.sii_result = "Proceso"
            if resp['SII:RESPUESTA']['SII:RESP_BODY']['RECHAZADOS'] == "1":
                self.sii_result = "Rechazado"
        elif resp['SII:RESPUESTA']['SII:RESP_HDR']['ESTADO'] == "RCT":
            self.sii_result = "Rechazado"
            _logger.info(resp)
            status = {'warning':{'title':_('Error RCT'), 'message': _(resp['SII:RESPUESTA']['SII:RESP_HDR']['GLOSA'])}}
        return status

    def _get_dte_status(self, signature_d, token):
        url = server_url[self.company_id.dte_service_provider] + 'QueryEstDte.jws?WSDL'
        ns = 'urn:'+ server_url[self.company_id.dte_service_provider] + 'QueryEstDte.jws'
        _server = SOAPProxy(url, ns)
        receptor = self.format_vat(self.commercial_partner_id.vat)
        date_invoice = datetime.strptime(self.date_invoice, "%Y-%m-%d").strftime("%d-%m-%Y")
        rut = signature_d['subject_serial_number']
        respuesta = _server.getEstDte(
            rut[:8],
            str(rut[-1]),
            self.company_id.vat[2:-1],
            self.company_id.vat[-1],
            receptor[:8],
            receptor[-1],
            str(self.sii_document_class_id.sii_code),
            str(self.sii_document_number),
            date_invoice,
            str(int(self.amount_total)),
            token,
        )
        self.sii_message = respuesta
        resp = xmltodict.parse(respuesta)
        if resp['SII:RESPUESTA']['SII:RESP_HDR']['ESTADO'] == '2':
            status = {'warning':{'title':_("Error code: 2"), 'message': _(resp['SII:RESPUESTA']['SII:RESP_HDR']['GLOSA'])}}
            return status
        if resp['SII:RESPUESTA']['SII:RESP_HDR']['ESTADO'] == "EPR":
            self.sii_result = "Proceso"
            if resp['SII:RESPUESTA']['SII:RESP_BODY']['RECHAZADOS'] == "1":
                self.sii_result = "Rechazado"
            if resp['SII:RESPUESTA']['SII:RESP_BODY']['REPARO'] == "1":
                self.sii_result = "Reparo"
        elif resp['SII:RESPUESTA']['SII:RESP_HDR']['ESTADO'] == "FAU":
            self.sii_result = "Rechazado"

    @api.multi
    def ask_for_dte_status(self):
        try:
            signature_d = self.get_digital_signature_pem(
                self.company_id)
            seed = self.get_seed(self.company_id)
            template_string = self.create_template_seed(seed)
            seed_firmado = self.sign_seed(
                template_string,
                signature_d['priv_key'],
                signature_d['cert'])
            token = self.get_token(seed_firmado,self.company_id)
        except AssertionError as e:
            raise UserError(str(e))
        if not self.sii_send_ident:
            raise UserError('No se ha enviado aún el documento, aún está en cola de envío interna en odoo')
        if self.sii_result == 'Enviado':
            status = self._get_send_status(self.sii_send_ident, signature_d, token)
            if self.sii_result != 'Proceso':
                return status
        return self._get_dte_status(signature_d, token)

class CesionDTEAR(models.Model):
    _name = 'account.invoice.imagen_ar'

    name = fields.Char(
        string='File Name',
    )
    image = fields.Binary(
        string='Imagen',
        filters='*.pdf,*.png, *.jpg',
        store=True,
        help='Upload Image',
    )
    invoice_id = fields.Many2one(
        'account.invoice',
        string="Factura",
    )
