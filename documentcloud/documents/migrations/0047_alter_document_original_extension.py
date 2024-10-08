# Generated by Django 3.2.9 on 2022-03-29 20:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0046_auto_20220307_1434'),
    ]

    operations = [
        migrations.AlterField(
            model_name='document',
            name='original_extension',
            field=models.CharField(choices=[('123', '123'), ('602', '602'), ('abw', 'abw'), ('agd', 'agd'), ('bmp', 'bmp'), ('cdr', 'cdr'), ('cgm', 'cgm'), ('cmx', 'cmx'), ('csv', 'csv'), ('cwk', 'cwk'), ('dbf', 'dbf'), ('dif', 'dif'), ('doc', 'doc'), ('docx', 'docx'), ('dot', 'dot'), ('emf', 'emf'), ('eps', 'eps'), ('fb2', 'fb2'), ('fhd', 'fhd'), ('fodg', 'fodg'), ('fodp', 'fodp'), ('fods', 'fods'), ('fodt', 'fodt'), ('gif', 'gif'), ('gnm', 'gnm'), ('gnumeric', 'gnumeric'), ('htm', 'htm'), ('html', 'html'), ('hwp', 'hwp'), ('jpeg', 'jpeg'), ('jpg', 'jpg'), ('jtd', 'jtd'), ('jtt', 'jtt'), ('key', 'key'), ('kth', 'kth'), ('mml', 'mml'), ('numbers', 'numbers'), ('odb', 'odb'), ('odf', 'odf'), ('odg', 'odg'), ('odp', 'odp'), ('ods', 'ods'), ('odt', 'odt'), ('p65', 'p65'), ('pages', 'pages'), ('pbm', 'pbm'), ('pcd', 'pcd'), ('pct', 'pct'), ('pcx', 'pcx'), ('pdf', 'pdf'), ('pgm', 'pgm'), ('plt', 'plt'), ('pm3', 'pm3'), ('pm4', 'pm4'), ('pm5', 'pm5'), ('pm6', 'pm6'), ('pmd', 'pmd'), ('png', 'png'), ('pot', 'pot'), ('ppm', 'ppm'), ('pps', 'pps'), ('ppt', 'ppt'), ('pptx', 'pptx'), ('psd', 'psd'), ('pub', 'pub'), ('qxp', 'qxp'), ('ras', 'ras'), ('rlf', 'rlf'), ('rtf', 'rtf'), ('sda', 'sda'), ('sdc', 'sdc'), ('sdd', 'sdd'), ('sdp', 'sdp'), ('sdw', 'sdw'), ('sgf', 'sgf'), ('sgl', 'sgl'), ('sgv', 'sgv'), ('slk', 'slk'), ('stc', 'stc'), ('std', 'std'), ('sti', 'sti'), ('stw', 'stw'), ('svg', 'svg'), ('svm', 'svm'), ('sxc', 'sxc'), ('sxd', 'sxd'), ('sxi', 'sxi'), ('sxm', 'sxm'), ('sxw', 'sxw'), ('tga', 'tga'), ('tif', 'tif'), ('tiff', 'tiff'), ('txt', 'txt'), ('uof', 'uof'), ('uop', 'uop'), ('uos', 'uos'), ('uot', 'uot'), ('vor', 'vor'), ('vsd', 'vsd'), ('wb2', 'wb2'), ('wdb', 'wdb'), ('wk1', 'wk1'), ('wk3', 'wk3'), ('wk4', 'wk4'), ('wks', 'wks'), ('wpd', 'wpd'), ('wps', 'wps'), ('wq1', 'wq1'), ('wq2', 'wq2'), ('wri', 'wri'), ('xbm', 'xbm'), ('xls', 'xls'), ('xlsx', 'xlsx'), ('xlt', 'xlt'), ('xlw', 'xlw'), ('xml', 'xml'), ('xpm', 'xpm'), ('zabw', 'zabw'), ('zmf', 'zmf')], default='pdf', help_text='The original extension of the underlying file', max_length=255, verbose_name='original extension'),
        ),
    ]
