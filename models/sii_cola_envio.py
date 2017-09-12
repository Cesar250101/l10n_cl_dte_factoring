# -*- coding: utf-8 -*-

from openerp import fields, models, api, _
import ast
import logging
_logger = logging.getLogger(__name__)

class ColaEnvio(models.Model):
    _inherit = "sii.cola_envio"

    tipo_trabajo = fields.Selection(selection_add=[('cesion','Cesion')])
    
    def _procesar_tipo_trabajo(self):
        if self.tipo_trabajo == 'cesion':
            docs = self.env[self.model].browse(ast.literal_eval(self.doc_ids))
            try:
                docs.do_cesion_dte_send()
                if docs[0].sii_cesion_result not in ['', 'NoEnviado']:
                    self.tipo_trabajo = 'consulta'
            except Exception as e:
                _logger.warning("Error en envío Cola")
                _logger.warning(str(e))
            return
        return super(ColaEnvio, self)._procesar_tipo_trabajo()
    