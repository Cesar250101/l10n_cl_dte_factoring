# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta, date
from lxml import etree
import pytz
import logging

_logger = logging.getLogger(__name__)

try:
    from facturacion_electronica import facturacion_electronica as fe
except Exception as e:
    _logger.warning("Problema al cargar Facturación electrónica: %s" % str(e))
try:
    from suds.client import Client
except ImportError:
    _logger.warning('Cannot import suds')

server_url = {
    'SIICERT': 'https://maullin.sii.cl/DTEWS/',
    'SII': 'https://palena.sii.cl/DTEWS/',
}


class CesionDTE(models.Model):
    _inherit = "account.invoice"

    cesion_number = fields.Integer(
        copy=False,
        string='Cesion Number',
        help='',
        default=1,
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
        ('Procesado', 'Procesado'),
        ('Cedido', 'Cedido'),
        ('Anulado', 'Anulado')],
        string='Resultado Cesion',
        copy=False,
        help="SII request result",
    )
    sii_cesion_request = fields.Many2one(
        'sii.xml.envio',
        string='SII XML Request',
        copy=False)
    sii_cesion_message = fields.Text(
        string='SII Message',
        copy=False,
    )
    sii_xml_cesion_response = fields.Text(
        string='SII XML Response',
        copy=False)
    imagen_ar_ids = fields.One2many(
        'account.invoice.imagen_ar',
        'invoice_id',
        string="Imagenes de acuse de recibo",
    )

    @api.onchange('cesionario_id')
    def set_declaracion(self):
        if self.cesionario_id:
            partner_id = self.commercial_partner_id or self.partner_id.commercial_partner_id
            declaracion_jurada = u'''Se declara bajo juramento que {0}, RUT {1} \
ha puesto a disposicion del cesionario {2}, RUT {3}, el o los documentos donde constan los recibos de las mercaderías entregadas o servicios prestados, \
entregados por parte del deudor de la factura {4}, RUT {5}, de acuerdo a lo establecido en la Ley No. 19.983'''.format(
                self.company_id.partner_id.name,
                self.company_id.partner_id.rut(),
                self.cesionario_id.commercial_partner_id.name,
                self.cesionario_id.commercial_partner_id.rut(),
                self.partner_id.commercial_partner_id.name,
                partner_id.rut(),
            )
            self.declaracion_jurada = declaracion_jurada

    @api.multi
    def get_cesion_xml_file(self):
        url_path = '/download/xml/cesion/%s' % (self.id)
        return {
            'type' : 'ir.actions.act_url',
            'url': url_path,
            'target': 'self',
        }

    def _id_dte(self):
        IdDoc = {}
        IdDoc['TipoDTE'] = self.document_class_id.sii_code
        IdDoc['RUTEmisor'] = self.company_id.partner_id.rut()
        if not self.partner_id.commercial_partner_id.vat:
            raise UserError("Debe Ingresar RUT Receptor")
        IdDoc['RznSocReceptor'] = self.partner_id.commercial_partner_id.name
        partner_id = self.commercial_partner_id or self.partner_id.commercial_partner_id
        IdDoc['RUTReceptor'] = partner_id.rut()
        IdDoc['Folio'] = self.get_folio()
        IdDoc['FchEmis'] = self.date_invoice
        IdDoc['MntTotal'] = self.currency_id.round(self.amount_total )
        return IdDoc

    def _cesionario(self):
        Receptor = {}
        if not self.cesionario_id.commercial_partner_id.vat:
            raise UserError("Debe Ingresar RUT Cesionario")
        Receptor['RUT'] = self.cesionario_id.commercial_partner_id.rut()
        Receptor['RazonSocial'] = self._acortar_str(self.cesionario_id.commercial_partner_id.name, 100)
        Receptor['Direccion'] = self._acortar_str((self.cesionario_id.street or self.cesionario_id.commercial_partner_id.street) + ' ' + (self.cesionario_id.street2 or self.cesionario_id.commercial_partner_id.street2 or ''),70)
        Receptor['eMail'] = self.cesionario_id.commercial_partner_id.email
        return Receptor

    def _monto_cesion(self):
        return self.currency_id.round(self.amount_total)

    def _cedente(self):
        Cedente = {
            'RUT': self.env.user.partner_id.rut(),
            'Nombre': self.env.user.name,
            'Phono': self.env.user.partner_id.phone,
            'eMail': self.env.user.partner_id.email,
        }
        return Cedente

    def _cesion(self):
        data = {
            'ID': 'C%s%s' % (self.document_class_id.doc_code_prefix, self.sii_document_number),
            'SeqCesion': self.cesion_number,
            'IdDTE': self._id_dte(),
            'Cedente': self._cedente(),
            'Cesionario': self._cesionario(),
            'MontoCesion': self._monto_cesion(),
            'UltimoVencimiento': self.date_invoice,
            'xml_dte': self.sii_xml_dte,
            'DeclaracionJurada': self.declaracion_jurada,
        }
        return data

    def _crear_envio_cesion(self):
        datos = self._get_datos_empresa(self.company_id)
        datos['filename'] = "AEC_1"
        datos['Cesion'] = self._cesion()
        return datos

    @api.multi
    def validate_cesion(self):
        for inv in self.with_context(lang='es_CL'):
            inv.sii_cesion_result = 'NoEnviado'
            if inv.type in ['out_invoice' ] and inv.document_class_id.sii_code in [33, 34]:
                if inv.journal_id.restore_mode:
                    inv.sii_result = 'Proceso'
                else:
                    datos = inv._crear_envio_cesion()
                    datos['test'] = True
                    fe.timbrar_y_enviar_cesion(datos)
                    inv.sii_cesion_result = 'EnCola'
                    self.env['sii.cola_envio'].create({
                                            'company_id': inv.company_id.id,
                                            'doc_ids': [inv.id],
                                            'model': 'account.invoice',
                                            'user_id': self.env.uid,
                                            'tipo_trabajo': 'cesion',
                                            })

    @api.multi
    def cesion_dte_send(self):
        if 1 == 1:#not self[0].sii_cesion_request or self[0].sii_cesion_result in ['Rechazado'] :
            for r in self:
                if r.sii_cesion_request:
                    r.sii_cesion_request.unlink()
            datos = self._crear_envio_cesion()
            result = fe.timbrar_y_enviar_cesion(datos)
            envio = {
                'xml_envio': result['sii_xml_request'],
                'name': result['sii_send_filename'],
                'company_id': self.company_id.id,
                'user_id': self.env.uid,
                'sii_send_ident': result['sii_send_ident'],
                'sii_xml_response': result['sii_xml_response'],
                'state': result['status'],
            }
            envio_id = self.env['sii.xml.envio'].create(envio)
            for r in self:
                r.sii_cesion_request = envio_id.id
                r.sii_cesion_result = result['status']
        return self[0].sii_cesion_request

    @api.multi
    def do_cesion_dte_send(self):
        ids = []
        for inv in self.with_context(lang='es_CL'):
            if inv.sii_cesion_result in ['', 'NoEnviado','Rechazado'] and inv.type in ['out_invoice' ] and inv.document_class_id.sii_code in [ 33, 34]:
                if inv.sii_cesion_result in ['Rechazado']:
                    inv._crear_envio_cesion()
                inv.sii_cesion_result = 'EnCola'
                ids.append(inv.id)
        if ids:
            self.env['sii.cola_envio'].create({
                                    'company_id': self[0].company_id.id,
                                    'doc_ids': ids,
                                    'model': 'account.invoice',
                                    'user_id': self.env.user.id,
                                    'tipo_trabajo': 'cesion',
                                    })

    def _get_cesion_dte_status(self):
        datos = self._get_datos_empresa(self.company_id)
        datos['Documento'] = []
        docs = {}
        for r in self:
            if r.sii_xml_request.state not in ['Aceptado', 'Rechazado']:
                continue
            docs.setdefault(self.document_class_id.sii_code, [])
            docs[self.document_class_id.sii_code].append(r._dte())
        if not docs:
            _logger.warning("En get_get_dte_status, no docs")
            return
        for k, v in docs.items():
            datos['Documento'].append ({
                'TipoDTE': k,
                'documentos': v
            })
        resultado = fe.consulta_estado_documento(datos)
        if not resultado:
            _logger.warning("En get_cesion_get_dte_status, no resultado")
            return
        for r in self:
            id = "T{}F{}".format(r.document_class_id.sii_code,
                                 r.sii_document_number)
            r.sii_cesion_result = resultado[id]['status']
            if resultado[id].get('xml_resp'):
                r.sii_cesion_message = resultado[id].get('xml_resp')

    def _get_datos_cesion_dte(self):
        url = server_url[self.company_id.dte_service_provider] + 'services/wsRPETCConsulta?wsdl'
        _server = Client(url)
        tenedor_rut = self.company_id.vat if self.sii_cesion_result == 'Cedido' else self.cesionario_id.vat
        respuesta = _server.service.getEstCesionRelac(
            token,
            rut[:-2],
            str(rut[-1]),
            str(self.document_class_id.sii_code),
            str(self.sii_document_number),
            tenedor_rut[2:-1],
            tenedor_rut[-1],
        )


    @api.multi
    def ask_for_cesion_dte_status(self):
        if not self.sii_cesion_request.sii_send_ident:
            raise UserError('No se ha enviado aún el documento, aún está en cola de envío interna en odoo')
        #if self.sii_cesion_result == 'Cedido':
        #    return self._get_datos_cesion_dte(
        #        signature_id.subject_serial_number,
        #        token,
        #    )
        if self.sii_cesion_request and self.sii_cesion_request.state == 'Enviado':
            status = self.sii_cesion_request.get_cesion_send_status()
            if self.sii_cesion_request.state != 'Aceptado':
                return status
        self.sii_cesion_result = self.sii_cesion_request.state
        try:
            return self._get_cesion_dte_status()
        except:
            pass

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
