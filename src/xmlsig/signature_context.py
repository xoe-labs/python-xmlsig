# -*- coding: utf-8 -*-
# © 2017 Creu Blanca
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtensionOID
from lxml import etree

from . import constants
from .constants import NS_MAP
from .utils import b64_print, get_rdns_name
from os import path


class SignatureContext(object):
    """
    Signature context is used to sign and verify Signature nodes with keys
    """

    def __init__(self):
        self.x509 = None
        self.crl = None
        self.private_key = None
        self.public_key = None
        self.key_name = None

    def sign(self, DS_Signature):
        """
        Signs a Signature node
        :param node: Signature node 
        :type node: lxml.etree.Element
        :return: None
        """
        signed_info = DS_Signature.find('ds:SignedInfo', namespaces=NS_MAP)
        signature_method = signed_info.find('ds:SignatureMethod',
                                            namespaces=NS_MAP).get(
            'Algorithm')
        key_info = DS_Signature.find('ds:KeyInfo', namespaces=NS_MAP)
        if key_info is not None:
            self._fill_key_info(key_info, signature_method)
        self._fill_signed_info(signed_info)
        self.calculate_signature(DS_Signature)

    def _fill_key_info(self, key_info, signature_method):
        """
        Fills the KeyInfo node
        :param key_info: KeyInfo node 
        :type key_info: lxml.etree.Element
        :param signature_method: Signature node to use
        :type signature_method: str
        :return: None
        """
        x509_data = key_info.find('ds:X509Data', namespaces=NS_MAP)
        if x509_data is not None:
            self._fill_x509_data(x509_data)
        key_name = key_info.find('ds:KeyName', namespaces=NS_MAP)
        if key_name is not None and self.key_name is not None:
            key_name.text = self.key_name
        key_value = key_info.find('ds:KeyValue', namespaces=NS_MAP)
        if key_value is not None:
            key_value.text = '\n'
            signature = constants.TransformUsageSignatureMethod[
                signature_method
            ]
            key = self.public_key
            if self.public_key is None:
                key = self.private_key.public_key()
            if not isinstance(
                    key, signature['method'].public_key_class
            ):
                raise Exception('Key not compatible with signature method')
            signature['method'].key_value(key_value, key)

    def _fill_x509_data(self, x509_data):
        """
        Fills the X509Data Node
        :param x509_data: X509Data Node
        :type x509_data: lxml.etree.Element
        :return: None
        """
        x509_issuer_serial = x509_data.find(
            'ds:X509IssuerSerial', namespaces=NS_MAP
        )
        if x509_issuer_serial is not None:
            self._fill_x509_issuer_name(x509_issuer_serial)

        x509_crl = x509_data.find('ds:X509CRL', namespaces=NS_MAP)
        if x509_crl is not None and self.crl is not None:
            x509_data.text = base64.b64encode(
                self.crl.public_bytes(serialization.Encoding.DER)
            )
        x509_subject = x509_data.find(
            'ds:X509SubjectName', namespaces=NS_MAP
        )
        if x509_subject is not None:
            x509_subject.text = get_rdns_name(self.x509.subject.rdns)
        x509_ski = x509_data.find('ds:X509SKI', namespaces=NS_MAP)
        if x509_ski is not None:
            x509_ski.text = base64.b64encode(
                self.x509.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_KEY_IDENTIFIER
                ).value.digest)
        x509_certificate = x509_data.find(
            'ds:X509Certificate', namespaces=NS_MAP
        )
        if x509_certificate is not None:
            certificate = self.x509.public_bytes(encoding=serialization.Encoding.DER)
            certificat_b64 = base64.b64encode(certificate)
            x509_certificate.text = b64_print(certificat_b64)  # Cosmetics

    def _fill_x509_issuer_name(self, x509_issuer_serial):
        """
        Fills the X509IssuerSerial node
        :param x509_issuer_serial: X509IssuerSerial node
        :type x509_issuer_serial: lxml.etree.Element
        :return: None
        """
        x509_issuer_name = x509_issuer_serial.find(
            'ds:X509IssuerName', namespaces=NS_MAP
        )
        if x509_issuer_name is not None:
            x509_issuer_name.text = get_rdns_name(self.x509.issuer.rdns)
        x509_issuer_number = x509_issuer_serial.find(
            'ds:X509SerialNumber', namespaces=NS_MAP
        )
        if x509_issuer_number is not None:
            x509_issuer_number.text = str(self.x509.serial_number)

    def _fill_signed_info(self, signed_info):
        """
        Fills the SignedInfo node
        :param signed_info: SignedInfo node
        :type signed_info: lxml.etree.Element
        :return: None
        """
        for reference in signed_info.findall('ds:Reference', namespaces=NS_MAP):
            self.calculate_reference(reference, True)

    def verify(self, DS_Signature):
        """
        Verifies a signature
        :param node: Signature node
        :type node: lxml.etree.Element
        :return: None
        """
        # Added XSD Validation
        with open(path.join(
                path.dirname(__file__), "data/xmldsig-core-schema.xsd"
        ), "rb") as file:
            schema = etree.XMLSchema(etree.fromstring(file.read()))
        schema.assertValid(DS_Signature)
        # Validates reference value
        signed_info = DS_Signature.find('ds:SignedInfo', namespaces=NS_MAP)
        for reference in signed_info.findall(
                'ds:Reference', namespaces=NS_MAP
        ):
            if not self.calculate_reference(reference, False):
                raise Exception(
                    'Reference with URI:"' +
                    reference.get("URI", '') +
                    '" failed'
                )
        # Validates signature value
        self.calculate_signature(DS_Signature, False)

    def transform_xmlsig1x(self, DS_transform, target):
        """
        Transforms a node following the transform especification
        :param DS_transform: Transform node
        :type DS_transform: lxml.etree.Element
        :param target: Element to transform
        :type target: lxml.etree.Element or octet-stream (Base64 method only)
        :return: Transformed node in a String
        """

        # XML Elements we work on
        algorithm = DS_transform.get('Algorithm')
        if algorithm == constants.TransformXmlSig2Tranform:
            raise NotImplementedError(
                "XML Signature 2.0 transforms are not implemented (yet)."
                "Please consider to submit an upstream PR")

        # By now, it is guaranteed to be an XML Signature 1.x Transform

        # Validate the transform algorithm
        if algorithm not in constants.TransformUsageDSigTransform:
            raise NotIMplementedError(
                "XML Signature 1.x Transform algorithm '{}' is not "
                "implemented (yet). Please consider to submit an "
                "upstream PR".format(algorithm))

        # C14N methods:
        # Canonicalize with additional canoncialization method
        if algorithm in constants.TransformUsageC14NMethod:
            return self.canonicalization(algorithm, target)

        # Enveloped method:
        # Remove parent <ds:Signature/> of this <ds:Transform/>
        if algorithm == constants.TransformEnveloped:
            signature = DS_transform.iterancestors('{*}Signature')[0]
            target.remove(signature)
            _algorithm = constants.TransformInclC14N,
            return self.canonicalization(_algorithm, target)

        # Base64 Method:
        # Base 64 decode the target's text element
        if algorithm == constants.TransformBase64:
            if isinstance(target, str):
                base64.b64decode(target)
            return base64.b64decode(target.text)

        raise Exception('Method not found')

    def canonicalization(self, method, node):
        """
        Canonicalizes a node following the method
        :param method: Method identification
        :type method: str
        :param node: object to canonicalize
        :type node: str
        :return: Canonicalized node in a String
        """
        if method not in constants.TransformUsageC14NMethod:
            raise Exception('Method not allowed: ' + method)
        c14n_method = constants.TransformUsageC14NMethod[method]
        return etree.tostring(
            node,
            method=c14n_method['method'],
            with_comments=c14n_method['comments'],
            exclusive=c14n_method['exclusive']
        )

    def digest(self, method, node):
        """
        Returns the digest of an object from a method name
        :param method: hash method
        :type method: str
        :param node: Object to hash
        :type node: str
        :return: hash result
        """
        if method not in constants.TransformUsageDigestMethod:
            raise Exception('Method not allowed')
        lib = hashlib.new(constants.TransformUsageDigestMethod[method])
        lib.update(node)
        return base64.b64encode(lib.digest())

    def get_uri(self, uri, reference):
        """
        It returns the node of the specified URI
        :param uri: uri of the 
        :type uri: str
        :param reference: Reference node
        :type reference: etree.lxml.Element
        :return: Element of the URI in a String
        """
        if uri == "":
            return self.canonicalization(
                constants.TransformInclC14N, reference.getroottree()
            )
        if uri.startswith("#"):
            query = "//*[@*[local-name() = '{}' ]=$uri]"
            node = reference.getroottree()
            results = self.check_uri_attr(node, query, uri, constants.ID_ATTR)
            if len(results) == 0:
                results = self.check_uri_attr(node, query, uri, 'ID')
            if len(results) == 0:
                results = self.check_uri_attr(node, query, uri, 'Id')
            if len(results) == 0:
                results = self.check_uri_attr(node, query, uri, 'id')
            if len(results) > 1:
                raise Exception(
                    "Ambiguous reference URI {} resolved to {} nodes".format(
                        uri, len(results)))
            elif len(results) == 1:
                return self.canonicalization(
                    constants.TransformInclC14N, results[0]
                )
        raise Exception('URI "' + uri + '" cannot be readed')

    def check_uri_attr(self, node, xpath_query, uri, attr):
        return node.xpath(xpath_query.format(attr), uri=uri.lstrip("#"))

    def calculate_reference(self, reference, sign=True):
        """
        Calculates or verifies the digest of the reference
        :param reference: Reference node
        :type reference: lxml.etree.Element
        :param sign: It marks if we must sign or check a signature
        :type sign: bool
        :return: None
        """
        node = self.get_uri(reference.get('URI', ''), reference)
        transforms = reference.find(
            'ds:Transforms', namespaces=constants.NS_MAP
        )
        if transforms is not None:
            for transform in transforms.findall(
                    'ds:Transform', namespaces=constants.NS_MAP
            ):
                node = self.transform(transform, etree.prase(node))
        digest_value = self.digest(
            reference.find(
                'ds:DigestMethod', namespaces=constants.NS_MAP
            ).get('Algorithm'),
            node
        )
        if not sign:
            return digest_value.decode() == reference.find(
                'ds:DigestValue', namespaces=constants.NS_MAP
            ).text

        reference.find(
            'ds:DigestValue', namespaces=constants.NS_MAP
        ).text = digest_value

    def calculate_signature(self, node, sign=True):
        """
        Calculate or verifies the signature
        :param node: Signature node
        :type node: lxml.etree.Element
        :param sign: It checks if it must calculate or verify
        :type sign: bool
        :return: None
        """
        signed_info_xml = node.find('ds:SignedInfo',
                                    namespaces=constants.NS_MAP)
        canonicalization_method = signed_info_xml.find(
            'ds:CanonicalizationMethod', namespaces=constants.NS_MAP
        ).get('Algorithm')
        signature_method = signed_info_xml.find(
            'ds:SignatureMethod', namespaces=constants.NS_MAP
        ).get('Algorithm')
        if signature_method not in constants.TransformUsageSignatureMethod:
            raise Exception('Method ' + signature_method + ' not accepted')
        signature = constants.TransformUsageSignatureMethod[signature_method]
        signed_info = self.canonicalization(
            canonicalization_method, signed_info_xml
        )
        if not sign:
            signature_value = node.find('ds:SignatureValue',
                                        namespaces=constants.NS_MAP).text
            public_key = signature['method'].get_public_key(node, self)
            signature['method'].verify(
                signature_value,
                signed_info,
                public_key,
                signature['digest']
            )
        else:
            node.find(
                'ds:SignatureValue', namespaces=constants.NS_MAP
            ).text = b64_print(base64.b64encode(
                signature['method'].sign(
                    signed_info,
                    self.private_key,
                    signature['digest']
                )
            ))

    def load_pkcs12(self, key):
        """
        This function fills the context public_key, private_key and x509 from 
        PKCS12 Object
        :param key: the PKCS12 Object
        :type key: OpenSSL.crypto.PKCS12
        :return: None
        """
        self.x509 = key.get_certificate().to_cryptography()
        self.public_key = key.get_certificate().to_cryptography().public_key()
        self.private_key = key.get_privatekey().to_cryptography_key()
