"""
IAM Identity Center Service for managing users and groups.

This service handles IAM Identity Center operations including:
- Creating users in Identity Center
- Managing group memberships
- Synchronizing with Cognito user creation
"""

import boto3
import logging
from typing import Optional, Dict, Any, List
from botocore.exceptions import ClientError
from dataclasses import dataclass


@dataclass
class IdentityCenterUser:
    """Identity Center user information."""
    user_id: str
    username: str
    email: str
    first_name: str
    last_name: str
    display_name: str


@dataclass
class IdentityCenterGroup:
    """Identity Center group information."""
    group_id: str
    group_name: str
    description: str


class IdentityCenterService:
    """
    Service for managing IAM Identity Center users and groups.
    
    This service provides:
    - User creation and management in Identity Center
    - Group creation and membership management
    - Integration with Cognito user signup process
    """
    
    def __init__(self, region: str = 'us-east-1'):
        """
        Initialize the Identity Center Service.
        
        Args:
            region: AWS region for Identity Center operations
        """
        self.region = region
        self.logger = logging.getLogger(__name__)
        
        try:
            self.identitystore_client = boto3.client('identitystore', region_name=region)
            self.sso_admin_client = boto3.client('sso-admin', region_name=region)
            self.ssm_client = boto3.client('ssm', region_name=region)
        except Exception as e:
            self.logger.error(f"Failed to initialize Identity Center clients: {str(e)}")
            raise
        
        # Cache for Identity Center instance and group information
        self._identity_store_id = None
        self._all_users_group_id = None
    
    def get_identity_store_id(self) -> Optional[str]:
        """
        Get the Identity Store ID from SSM parameter (set during CloudFormation).
        
        Returns:
            Identity Store ID if found, None otherwise
        """
        if self._identity_store_id:
            return self._identity_store_id
        
        try:
            # Get identity store ID from SSM parameter (set by CloudFormation)
            response = self.ssm_client.get_parameter(
                Name='/icode/identity-center/identity-store-id'
            )
            self._identity_store_id = response['Parameter']['Value']
            self.logger.info(f"Retrieved Identity Store ID: {self._identity_store_id}")
            return self._identity_store_id
            
        except ClientError as e:
            self.logger.error(f"Failed to get Identity Store ID from SSM: {e}")
            self.logger.error("Make sure the CDK stack has been deployed to create the Identity Center group")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error getting Identity Store ID: {str(e)}")
            return None
    
    def get_all_users_group_id(self) -> Optional[str]:
        """
        Get the allIcodeUsers group ID from SSM parameter (created during CloudFormation).
        
        Returns:
            Group ID if found, None otherwise
        """
        if self._all_users_group_id:
            return self._all_users_group_id
        
        try:
            # Get group ID from SSM parameter (set by CloudFormation)
            response = self.ssm_client.get_parameter(
                Name='/icode/identity-center/all-users-group-id'
            )
            self._all_users_group_id = response['Parameter']['Value']
            self.logger.info(f"Retrieved allIcodeUsers group ID: {self._all_users_group_id}")
            return self._all_users_group_id
            
        except ClientError as e:
            self.logger.error(f"Failed to get allIcodeUsers group ID from SSM: {e}")
            self.logger.error("Make sure the CDK stack has been deployed to create the Identity Center group")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error getting group ID: {str(e)}")
            return None
    
    def create_user(self, username: str, email: str, first_name: str, last_name: str) -> Optional[IdentityCenterUser]:
        """
        Create a user in IAM Identity Center.
        
        Args:
            username: Username for the user
            email: Email address
            first_name: First name
            last_name: Last name
            
        Returns:
            IdentityCenterUser object if successful, None otherwise
        """
        identity_store_id = self.get_identity_store_id()
        if not identity_store_id:
            self.logger.error("Cannot create user: Identity Store ID not available")
            return None
        
        try:
            # Check if user already exists
            try:
                existing_response = self.identitystore_client.get_user_id(
                    IdentityStoreId=identity_store_id,
                    AlternateIdentifier={
                        'UniqueAttribute': {
                            'AttributePath': 'UserName',
                            'AttributeValue': username
                        }
                    }
                )
                
                # User already exists, return existing user info
                user_response = self.identitystore_client.describe_user(
                    IdentityStoreId=identity_store_id,
                    UserId=existing_response['UserId']
                )
                
                return IdentityCenterUser(
                    user_id=existing_response['UserId'],
                    username=user_response['UserName'],
                    email=user_response.get('Emails', [{}])[0].get('Value', email),
                    first_name=user_response.get('Name', {}).get('GivenName', first_name),
                    last_name=user_response.get('Name', {}).get('FamilyName', last_name),
                    display_name=user_response.get('DisplayName', f"{first_name} {last_name}")
                )
                
            except ClientError:
                # User doesn't exist, create new one
                pass
            
            # Create new user
            display_name = f"{first_name} {last_name}"
            
            response = self.identitystore_client.create_user(
                IdentityStoreId=identity_store_id,
                UserName=username,
                DisplayName=display_name,
                Name={
                    'GivenName': first_name,
                    'FamilyName': last_name,
                    'Formatted': display_name
                },
                Emails=[
                    {
                        'Value': email,
                        'Type': 'work',
                        'Primary': True
                    }
                ]
            )
            
            user_id = response['UserId']
            
            self.logger.info(f"Created Identity Center user: {username} with ID: {user_id}")
            
            return IdentityCenterUser(
                user_id=user_id,
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                display_name=display_name
            )
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'ConflictException':
                self.logger.warning(f"User {username} already exists in Identity Center")
                # Try to get existing user info
                try:
                    existing_response = self.identitystore_client.get_user_id(
                        IdentityStoreId=identity_store_id,
                        AlternateIdentifier={
                            'UniqueAttribute': {
                                'AttributePath': 'UserName',
                                'AttributeValue': username
                            }
                        }
                    )
                    return self.get_user_by_id(existing_response['UserId'])
                except ClientError:
                    pass
            else:
                self.logger.error(f"Failed to create Identity Center user: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error creating Identity Center user: {str(e)}")
            return None
    
    def add_user_to_all_users_group(self, user_id: str) -> bool:
        """
        Add a user to the allIcodeUsers group.
        
        Args:
            user_id: Identity Center user ID
            
        Returns:
            True if successful, False otherwise
        """
        identity_store_id = self.get_identity_store_id()
        if not identity_store_id:
            self.logger.error("Cannot add user to group: Identity Store ID not available")
            return False
        
        group_id = self.get_all_users_group_id()
        if not group_id:
            self.logger.error("Cannot add user to group: allIcodeUsers group ID not available")
            return False
        
        try:
            # Check if user is already in the group
            try:
                memberships = self.identitystore_client.list_group_memberships_for_member(
                    IdentityStoreId=identity_store_id,
                    MemberId={
                        'UserId': user_id
                    }
                )
                
                for membership in memberships.get('GroupMemberships', []):
                    if membership['GroupId'] == group_id:
                        self.logger.info(f"User {user_id} is already in allIcodeUsers group")
                        return True
                        
            except ClientError:
                pass  # Continue to add membership
            
            # Add user to group
            self.identitystore_client.create_group_membership(
                IdentityStoreId=identity_store_id,
                GroupId=group_id,
                MemberId={
                    'UserId': user_id
                }
            )
            
            self.logger.info(f"Added user {user_id} to allIcodeUsers group")
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'ConflictException':
                self.logger.info(f"User {user_id} is already in allIcodeUsers group")
                return True
            else:
                self.logger.error(f"Failed to add user to allIcodeUsers group: {e}")
                return False
        except Exception as e:
            self.logger.error(f"Unexpected error adding user to group: {str(e)}")
            return False
    
    def get_user_by_id(self, user_id: str) -> Optional[IdentityCenterUser]:
        """
        Get user information by user ID.
        
        Args:
            user_id: Identity Center user ID
            
        Returns:
            IdentityCenterUser object if found, None otherwise
        """
        identity_store_id = self.get_identity_store_id()
        if not identity_store_id:
            return None
        
        try:
            response = self.identitystore_client.describe_user(
                IdentityStoreId=identity_store_id,
                UserId=user_id
            )
            
            emails = response.get('Emails', [])
            primary_email = next((email['Value'] for email in emails if email.get('Primary')), 
                                emails[0]['Value'] if emails else '')
            
            name = response.get('Name', {})
            
            return IdentityCenterUser(
                user_id=user_id,
                username=response['UserName'],
                email=primary_email,
                first_name=name.get('GivenName', ''),
                last_name=name.get('FamilyName', ''),
                display_name=response.get('DisplayName', '')
            )
            
        except ClientError as e:
            self.logger.error(f"Failed to get user by ID: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error getting user by ID: {str(e)}")
            return None
    
    def create_user_and_add_to_group(self, username: str, email: str, first_name: str, last_name: str) -> Optional[IdentityCenterUser]:
        """
        Create a user and add them to the allIcodeUsers group in one operation.
        
        Args:
            username: Username for the user
            email: Email address
            first_name: First name
            last_name: Last name
            
        Returns:
            IdentityCenterUser object if successful, None otherwise
        """
        self.logger.info(f"Starting Identity Center user creation for: {username}")
        
        # Create the user
        user = self.create_user(username, email, first_name, last_name)
        if not user:
            self.logger.error(f"Failed to create Identity Center user: {username}")
            return None
        
        self.logger.info(f"Successfully created Identity Center user: {username} with ID: {user.user_id}")
        
        # Add to allIcodeUsers group (created by CloudFormation)
        success = self.add_user_to_all_users_group(user.user_id)
        if not success:
            self.logger.error(f"Created user {username} but failed to add to allIcodeUsers group")
            # Still return the user object since user creation succeeded
        else:
            self.logger.info(f"Successfully added user {username} to allIcodeUsers group")
        
        return user