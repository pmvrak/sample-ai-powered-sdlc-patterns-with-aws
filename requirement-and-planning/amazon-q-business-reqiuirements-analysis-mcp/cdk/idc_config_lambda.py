import json
import boto3
import cfnresponse

sso_admin_client = boto3.client('sso-admin')

def app_access_scope(action, res_props):
    idc_app_arn = res_props.get('IDCApplicationArn')
    access_scopes = res_props.get('AccessScopes')
    for access_scope in access_scopes:
        match action:
            case "put":
                sso_admin_client.put_application_access_scope(
                    ApplicationArn=idc_app_arn,
                    Scope=access_scope
                )
            case "delete":
                sso_admin_client.delete_application_access_scope(
                    ApplicationArn=idc_app_arn,
                    Scope=access_scope
                )
    return f"[{idc_app_arn}][{','.join(access_scopes)}]"

def app_assignment_config(action, res_props):
    idc_app_arn = res_props.get('IDCApplicationArn')
    is_required = res_props.get('AssignmentRequired', 'no') == 'yes'
    if action == "put":
        sso_admin_client.put_application_assignment_configuration(
            ApplicationArn=idc_app_arn,
            AssignmentRequired=is_required
        )
    return f"[{idc_app_arn}][required={is_required}]"

def app_auth_method(action, res_props):
    idc_app_arn = res_props.get('IDCApplicationArn')
    auth_method = res_props.get('AuthenticationMethod')
    resource_list = list(map(
        lambda x: json.dumps(x['Resource']),
        auth_method['Iam']['ActorPolicy']['Statement']
    ))
    match action:
        case "put":
            sso_admin_client.put_application_authentication_method(
                ApplicationArn=idc_app_arn,
                AuthenticationMethodType='IAM',
                AuthenticationMethod=auth_method
            )
        case "delete":
            sso_admin_client.delete_application_authentication_method(
                ApplicationArn=idc_app_arn,
                AuthenticationMethodType='IAM'
            )
    return f"[{idc_app_arn}][IAM][{','.join(resource_list)}]"

def tt_issuer(action, res_props, phy_res_id):
    name = res_props.get('Name')
    idc_inst_arn = res_props.get('InstanceArn')
    tti_config = res_props.get('TTIConfiguration')
    data = {}
    match action:
        case "put":
            resp = sso_admin_client.create_trusted_token_issuer(
                Name=name,
                InstanceArn=idc_inst_arn,
                TrustedTokenIssuerType='OIDC_JWT',
                TrustedTokenIssuerConfiguration=tti_config
            )
            phy_res_id = resp['TrustedTokenIssuerArn']
            data = resp
        case "update":
            tti_config['OidcJwtConfiguration'].pop('IssuerUrl', None)
            sso_admin_client.update_trusted_token_issuer(
                Name=name,
                TrustedTokenIssuerArn=phy_res_id,
                TrustedTokenIssuerConfiguration=tti_config
            )
        case "delete":
            sso_admin_client.delete_trusted_token_issuer(
                TrustedTokenIssuerArn=phy_res_id
            )
    return phy_res_id, data

def app_grant(action, res_props):
    idc_app_arn = res_props.get('IDCApplicationArn')
    grant_type = res_props.get('GrantType')
    grant = res_props.get('Grant')
    match action:
        case "put":
            sso_admin_client.put_application_grant(
                ApplicationArn=idc_app_arn,
                GrantType=grant_type,
                Grant=grant
            )
        case "delete":
            sso_admin_client.delete_application_grant(
                ApplicationArn=idc_app_arn,
                GrantType=grant_type
            )
    return f"[{idc_app_arn}][{json.dumps(grant['JwtBearer']['AuthorizedTokenIssuers'])}]"

def handler(event, context):
    try:
        print('Received event: ' + json.dumps(event, indent=4, default=str))
        request_type = event.get('RequestType')
        if not request_type:
            raise Exception("Missing request type")
        res_props = event.get('ResourceProperties')
        if not res_props:
            raise Exception("Missing resource properties")
        old_res_props = event.get('OldResourceProperties')
        if request_type == "Update" and not old_res_props:
            raise Exception("Missing old resource properties")
        resource_type = res_props.get('ResourceType')
        if not resource_type:
            raise Exception("Missing resource type")
        data = {}
        phy_res_id = event.get('PhysicalResourceId')
        match resource_type:
            case "access-scope":
                match request_type:
                    case "Create":
                        phy_res_id = app_access_scope("put", res_props)
                    case "Update":
                        phy_res_id = app_access_scope("delete", old_res_props)
                        phy_res_id = app_access_scope("put", res_props)
                    case "Delete":
                        phy_res_id = app_access_scope("delete", res_props)
            case "assignment-config":
                match request_type:
                    case "Create" | "Update":
                        phy_res_id = app_assignment_config("put", res_props)
            case "app-auth-method":
                match request_type:
                    case "Create" | "Update":
                        phy_res_id = app_auth_method("put", res_props)
                    case "Delete":
                        phy_res_id = app_auth_method("delete", res_props)
            case "trusted-token-issuer":
                match request_type:
                    case "Create":
                        phy_res_id, data = tt_issuer("put", res_props, phy_res_id)
                    case "Update":
                        phy_res_id, data = tt_issuer("update", res_props, phy_res_id)
                    case "Delete":
                        phy_res_id, data = tt_issuer("delete", res_props, phy_res_id)
            case "application-grant":
                match request_type:
                    case "Create" | "Update":
                        phy_res_id = app_grant("put", res_props)
                    case "Delete":
                        phy_res_id = app_grant("delete", res_props)
            case _:
                raise Exception("Unsupported resource type.")
        cfnresponse.send(event, context, cfnresponse.SUCCESS, data, phy_res_id)
    except Exception as e:
        print(e)
        cfnresponse.send(event, context, cfnresponse.FAILED, {})