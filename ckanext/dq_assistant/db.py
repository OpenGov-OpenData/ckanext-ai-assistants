import logging

import sqlalchemy as sa

from ckan.model.meta import metadata, mapper, Session
from ckan.model.domain_object import DomainObject


log = logging.getLogger(__name__)

__all__ = ['DataQualityReports', 'data_quality_reports']

data_quality_reports = None


def init_db():
    if data_quality_reports is None:
        define_data_quality_reports()
        log.debug('DataQualityReports table defined in memory')

    if not data_quality_reports.exists():
        data_quality_reports.create(checkfirst=True)
        log.debug('data_quality_reports table created')
    else:
        log.debug('data_quality_reports table already exist')


class DataQualityReports(DomainObject):
    @classmethod
    def by_resource_id(cls, resource_id):
        return Session.query(cls).filter_by(resource_id=resource_id).first()


def define_data_quality_reports():
    global data_quality_reports

    data_quality_reports = sa.Table(
        'data_quality_reports', metadata,
        sa.Column('resource_id', sa.UnicodeText, sa.ForeignKey("resource.id"), primary_key=True),
        sa.Column('data', sa.LargeBinary),
        sa.Column('created', sa.TIMESTAMP, server_default=sa.sql.func.now()),
    )

    mapper(DataQualityReports, data_quality_reports)
