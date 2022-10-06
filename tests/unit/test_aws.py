if __name__ == '__main__':
    import os
    from kensu import requests
    from kensu.utils.kensu_provider import KensuProvider
    import kensu.boto3 as boto3

    ## kensu setup
    offline = True
    api_url = os.environ.get('KSU_KENSU_INGESTION_URL') or ''
    auth_token = os.environ.get('KSU_KENSU_INGESTION_TOKEN') or ''
    kensu = KensuProvider().initKensu(init_context=True,
                                      kensu_ingestion_url=api_url,
                                      kensu_ingestion_token=auth_token,
                                      report_to_file=offline,
                                      project_names=['aws s3'],
                                      offline_file_name='kensu-offline-to-aws-s3-test.jsonl',
                                      mapping=True, report_in_mem=False)
    #### end of kensu setup

    response = requests.get(url="http://api.open-notify.org/astros.json")

    S3 = boto3.resource('s3', region_name='eu-west-1')

    s3_obj_name = 'test-file-v'
    s3_obj = S3.Object(os.environ.get('S3_BUCKET_NAME'), s3_obj_name)
    s3_obj.put(Body = response.text)
